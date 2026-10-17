import logging
import posixpath
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlsplit

from django.core.cache import cache
from django.core.files import File
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
import requests

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, STORAGE_PREFIX
from .helpers import (
    download_to_tempfile,
    get_cached_cors_allow_list,
    get_cloud_media_root,
    is_transient_download_error,
)
from .resource import Resource, resource_cors_cache_key

ROLE_MAX_LENGTH = 255

logger = logging.getLogger("django")


class ExternalResourceLocalizeException(Exception):
    pass


def is_permanent_localize_error(e: Exception) -> bool:
    """Whether localizing would fail the same way if retried: the format is
    gone, it can't be localized safely, or a download failed for good (e.g.
    404)."""
    if isinstance(e, (Format.DoesNotExist, ExternalResourceLocalizeException)):
        return True
    if isinstance(e, requests.RequestException):
        return not is_transient_download_error(e)
    return False


def common_url_dir(paths: List[str]) -> str:
    """Longest common directory of URL paths. Unlike posixpath.commonpath this
    keeps empty segments, which archive.org URLs contain
    (/web/<timestamp>/https://host/...)."""
    common = []
    for parts in zip(*[path.split("/") for path in paths]):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    return "/".join(common)



def format_cors_cache_key(format_pk, resource_pks, cors_allow_list) -> str:
    """Cache key for Format.is_cors_allowed. The pks are sorted because they
    come from an unordered UNION query, whose order isn't guaranteed to be
    the same when the value is cached as when it is cleared."""
    pks = "-".join(str(pk) for pk in sorted(resource_pks))
    return f"format_is_cors_allowed-{format_pk}-{pks}-{cors_allow_list}"


def clear_cors_cache(format, resources: List[Resource]):
    """Clear the cached is_cors_allowed values for a format and its
    resources, which are cached with no expiry."""
    cors_allow_list = get_cached_cors_allow_list()
    pks = {r.pk for r in resources}
    cache.delete_many(
        [resource_cors_cache_key(pk, cors_allow_list) for pk in pks]
        + [format_cors_cache_key(format.pk, pks, cors_allow_list)]
    )

def url_relative_path(url: str, base_url: Optional[str]) -> Optional[str]:
    """Path of `url` relative to directory `base_url`, without query string or
    fragment, or None if `url` isn't under `base_url`."""
    if not base_url or not url.startswith(base_url):
        return None
    rel = url[len(base_url):]
    return unquote(rel.split("?", 1)[0].split("#", 1)[0])


def storage_dir_in_use(storage, path: str) -> bool:
    """Whether anything exists at directory `path`. On a filesystem an empty
    directory counts; object stores such as S3 have no directories, so there
    a prefix is in use only if objects exist under it."""
    try:
        dirs, files = storage.listdir(path)
    except FileNotFoundError:
        return False
    return bool(dirs or files) or storage.exists(path)


class Format(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    format_type = models.CharField(max_length=255)
    zip_archive_url = models.CharField(max_length=FILENAME_MAX_LENGTH, null=True, blank=True)
    triangle_count = models.PositiveIntegerField(null=True, blank=True)
    lod_hint = models.PositiveIntegerField(null=True, blank=True)
    role = models.CharField(
        max_length=ROLE_MAX_LENGTH,
        null=True,
        blank=True,
    )
    root_resource = models.ForeignKey(
        "Resource",
        null=True,
        blank=True,
        related_name="root_formats",
        on_delete=models.SET_NULL,
    )
    is_preferred_for_gallery_viewer = models.BooleanField(default=False)
    is_preferred_for_download = models.BooleanField(default=True)

    def add_root_resource(self, resource):
        if not resource.format:
            from icosa.api.exceptions import RootResourceException

            raise RootResourceException("Resource must have a format associated with it.")
        self.root_resource = resource
        resource.format = None
        resource.save()
        self.save()

    async def aadd_root_resource(self, resource):
        if not resource.format:
            from icosa.api.exceptions import RootResourceException

            raise RootResourceException("Resource must have a format associated with it.")
        self.root_resource = resource
        resource.format = None
        await resource.asave()
        await self.asave()

    def get_resources(self, query: Q = Q(), exclude_q: Optional[Q] = None):
        resources = self.resource_set.filter(query)
        if exclude_q is not None:
            resources = resources.exclude(exclude_q)
        if self.root_resource:
            # We can only union on another queryset, even though we just want one
            # instance.
            root_resource = Resource.objects.filter(pk=self.root_resource.pk)
            resources = resources.union(root_resource)
        return resources

    def get_all_resources(self, query: Q = Q()):
        return self.get_resources(query)

    def get_non_image_resources(self, query: Q = Q()):
        exclude_q = Q()
        for ext in [".png", ".jpg", ".jpeg"]:
            exclude_q |= Q(file__endswith=ext)
        return self.get_resources(query, exclude_q)

    def get_resource_data(self, resources: List[Resource]):
        local_files = []
        for r in resources:
            if not r.file:
                continue
            if r.uploaded_file_path:
                full_path = str(Path(r.uploaded_file_path).parent)
            else:
                full_path = ""
            local_files.append([f"{STORAGE_PREFIX}{r.file.name}", full_path])

        if all([x.is_cors_allowed and x.remote_host for x in resources]):
            external_files = [[x.external_url, ""] for x in resources if x.external_url]
            resource_data = {
                "files_to_zip": external_files + local_files,
            }
        elif all([x.file for x in resources]):
            resource_data = {"files_to_zip": local_files}
        else:
            resource_data = {}
        return resource_data

    def localize_external_resources(self, **download_kwargs) -> List[Resource]:
        """Download every resource of this format that is only stored
        externally (e.g. on archive.org), upload it to the configured Django
        storage and update the resource so it is no longer external.

        The directory layout relative to the root resource is preserved so
        that relative references between files (e.g. a gltf pointing at its
        bin and textures) keep working. If the root itself is already stored
        locally, nothing is downloaded: each resource is linked to the file
        of the same relative path alongside it, and the format is refused if
        any is missing.

        All downloads happen before anything is written, and the database is
        only updated once every upload has succeeded, so a failure part way
        through leaves the format unchanged and removes files uploaded by
        that attempt. `download_kwargs` are passed to `download_to_tempfile`.

        Returns the list of resources that were localized.
        """
        root = self.root_resource
        resources = list(self.resource_set.all())
        if root is not None:
            resources.append(root)
        external = [r for r in resources if r.external_url and not r.file]
        if not external and not self.zip_archive_url:
            # Nothing left to do, but a previous attempt may have committed
            # and then failed before clearing the cache at the end, so clear
            # it here too.
            clear_cors_cache(self, resources)
            return []

        # Work out every path relative to the root before changing anything,
        # since Resource.relative_path changes once the root has a file.
        base_url = None
        if root is not None and root.external_url:
            base_url = f"{root.external_url.rsplit('/', 1)[0]}/"
            if not root.file:
                root_url = urlsplit(root.external_url)
                source_urls = [urlsplit(r.external_url) for r in external]
                source_dirs = [
                    posixpath.dirname(url.path)
                    for url in source_urls
                    if (url.scheme, url.netloc) == (root_url.scheme, root_url.netloc)
                ]
                base_path = common_url_dir(source_dirs)
                base_url = root_url._replace(path=f"{base_path.rstrip('/')}/", query="", fragment="").geturl()

        # Only files under the root's directory have a known place in the
        # layout; anything else (e.g. on another host) can't be placed safely.
        relative_paths = {}
        for r in external:
            rel = url_relative_path(r.external_url, base_url)
            if rel is None:
                raise ExternalResourceLocalizeException(
                    f"{r.external_url} is not under the root resource's directory {base_url}"
                )
            relative_paths[r.external_url] = rel

        # Several resources may share a URL; each URL is fetched and stored once.
        tmp_files = {}
        saved_names = {}
        uploaded_files = []
        original_values = {
            r.pk: (r.file.name, r.uploaded_file_path, r.external_url) for r in external
        }
        original_archive_url = self.zip_archive_url
        original_root_url = root.external_url if root is not None else None
        try:
            storage = Resource._meta.get_field("file").storage
            if root is not None and root.file:
                # The root is already stored, with the files it refers to
                # uploaded alongside it (e.g. the model_(GLTFupdated).gltf roots
                # from the Poly import). Those are what the viewer loads, and
                # they can differ from the external originals, so link to them
                # rather than downloading.
                root_dir = posixpath.dirname(root.file.name)
                for url, rel in relative_paths.items():
                    name = f"{root_dir}/{rel}"
                    if not storage.exists(name):
                        raise ExternalResourceLocalizeException(
                            f"{name} does not exist alongside the local root file {root.file.name}"
                        )
                    saved_names[url] = name
            else:
                # Storage paths need an owner. Asset.owner is nullable although
                # no ownerless assets are known; check before downloading.
                owner_id = self.asset.owner_id
                if owner_id is None:
                    raise ExternalResourceLocalizeException(f"Asset {self.asset.id} has no owner")
                for url in relative_paths:
                    tmp_files[url] = download_to_tempfile(url, **download_kwargs)

                # Never write into a directory that already has anything in
                # it, so existing files (another format of the same type, a
                # normal upload, leftovers from an interrupted attempt) are
                # never overwritten. The whole format moves together so
                # relative references between its files still resolve.
                base_dir = f"{get_cloud_media_root()}{owner_id}/{self.asset.id}/{self.format_type}"
                target_dir = base_dir
                suffix = 1
                while storage_dir_in_use(storage, target_dir):
                    suffix += 1
                    target_dir = f"{base_dir}_{suffix}"

                for url, rel in relative_paths.items():
                    # Unlike format_upload_path, keep every file's original
                    # name (including the root's) so the stored layout mirrors
                    # the source.
                    name = f"{target_dir}/{rel}"
                    # Save via the storage rather than FieldFile.save, which
                    # would run get_valid_name and mangle names (e.g. spaces)
                    # that other files in the format refer to.
                    saved_name = storage.save(name, File(tmp_files[url]))
                    uploaded_files.append((storage, saved_name))
                    if saved_name != name:
                        raise ExternalResourceLocalizeException(
                            f"Storage saved {name} as {saved_name}; relative references would break."
                        )
                    saved_names[url] = saved_name

            for r in external:
                r.uploaded_file_path = relative_paths[r.external_url]
                r.file.name = saved_names[r.external_url]

            # Only write the fields this changes: the instances were loaded
            # before the downloads, and other fields may have been edited
            # since. Localizing is bookkeeping, so update_time is left alone.
            with transaction.atomic():
                for r in external:
                    r.external_url = None
                    r.save(update_fields=["file", "uploaded_file_path", "external_url"])
                # A local file takes precedence over external_url, which for a
                # local root was only kept so Resource.get_base_path could
                # place resources that were still external.
                if root is not None and root.file and root.external_url:
                    root.external_url = None
                    root.save(update_fields=["external_url"])
                # The archive is also externally hosted; once every resource is
                # local, downloads can be served from our own storage instead.
                # A format with no resources keeps it: it's the only download.
                if self.zip_archive_url and resources and all(r.file for r in resources):
                    self.zip_archive_url = None
                    self.save(update_fields=["zip_archive_url"], update_timestamps=False)
        except BaseException:
            # BaseException so an interrupted run (Ctrl+C) also cleans up.
            for r in external:
                r.file.name, r.uploaded_file_path, r.external_url = original_values[r.pk]
            self.zip_archive_url = original_archive_url
            if root is not None:
                root.external_url = original_root_url
            for storage, saved_name in reversed(uploaded_files):
                # Keep going and re-raise the original error, not this one.
                try:
                    storage.delete(saved_name)
                except Exception as e:
                    logger.error(f"[localize] Format {self.pk}: failed to delete {saved_name} during cleanup: {e}")
            raise
        finally:
            for tmp in tmp_files.values():
                tmp.close()

        clear_cors_cache(self, resources)
        return external

    def user_label(self):
        # If self.role is None, then we avoid a db lookup by returning early.
        if self.role is None:
            return self.format_type.lower()
        role_label = FormatRoleLabel.objects.filter(role_text=self.role).first()
        if role_label is None:
            return self.format_type.lower()
        return role_label.label

    @property
    def is_cors_allowed(self):
        cors_allow_list = get_cached_cors_allow_list()
        resources = self.get_all_resources()
        cache_key = format_cors_cache_key(self.pk, [x.pk for x in resources], cors_allow_list)

        is_allowed = cache.get(cache_key, None)

        if is_allowed is not None:
            return is_allowed

        # We got nothing back from the cache; let's compute the value.
        disallowed_list = [not x.is_cors_allowed for x in resources]
        is_disallowed = any(disallowed_list)

        # NOTE(james): Purely so I leave parsing double-negatives in my head until the very end.
        is_allowed = not is_disallowed
        cache.set(cache_key, is_allowed, None)  # No expiry
        return is_allowed

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "role",
                    "is_preferred_for_gallery_viewer",
                    "is_preferred_for_download",
                ]
            )
        ]


class FormatRoleLabel(models.Model):
    """This model is responsible for creating a user-facing label for a
    format's role. There is no requirement for these records to be filled in.
    User-facing format display implementations should either use a format's
    format_type, or a friendly version of role.

    See Format.user_label for an example of an implementation.
    """

    create_time = models.DateTimeField()
    update_time = models.DateTimeField(null=True, blank=True)
    role_text = models.CharField(max_length=ROLE_MAX_LENGTH)
    label = models.CharField(max_length=1024)

    def save(self, *args, **kwargs):
        update_timestamps = kwargs.pop("update_timestamps", True)
        now = timezone.now()
        if self._state.adding:
            self.create_time = now
        else:
            if update_timestamps:
                self.update_time = now
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.role_text} => {self.label}"
