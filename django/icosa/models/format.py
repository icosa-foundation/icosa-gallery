from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

from django.core.cache import cache
from django.core.files import File
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .asset import Asset
from .common import FILENAME_MAX_LENGTH, STORAGE_PREFIX
from .helpers import (
    download_to_tempfile,
    format_upload_path,
    get_cached_cors_allow_list,
)
from .resource import Resource

ROLE_MAX_LENGTH = 255


class ExternalResourceLocalizeException(Exception):
    pass


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
        bin and textures) keep working.

        All downloads happen before anything is written, and the database is
        only updated once every upload has succeeded, so a failure part way
        through leaves the format unchanged (aside from possibly orphaned
        files in storage). `download_kwargs` are passed to
        `download_to_tempfile`.

        Returns the list of resources that were localized.
        """
        root = self.root_resource
        resources = list(self.resource_set.all())
        if root is not None:
            resources.append(root)
        external = [r for r in resources if r.external_url and not r.file]
        if not external and not self.zip_archive_url:
            return []

        # Work out every path relative to the root before changing anything,
        # since Resource.relative_path changes once the root has a file.
        base_url = None
        if root is not None and root.external_url:
            base_url = f"{root.external_url.rsplit('/', 1)[0]}/"

        relative_paths = {}
        for r in external:
            if r.pk != getattr(root, "pk", None) and base_url and r.external_url.startswith(base_url):
                rel = r.external_url[len(base_url):]
            else:
                rel = r.external_url.rsplit("/", 1)[-1]
            relative_paths[r.pk] = unquote(rel.split("?", 1)[0])

        tmp_files = {}
        try:
            for r in external:
                tmp_files[r.pk] = download_to_tempfile(r.external_url, **download_kwargs)

            for r in external:
                rel = relative_paths[r.pk]
                # format_upload_path uses this to recreate subdirectories.
                r.uploaded_file_path = rel
                name = format_upload_path(r, rel.rsplit("/", 1)[-1])
                # Save via the storage rather than FieldFile.save, which would
                # run get_valid_name and mangle names (e.g. spaces) that other
                # files in the format refer to.
                saved_name = r.file.storage.save(name, File(tmp_files[r.pk]))
                if saved_name != name:
                    raise ExternalResourceLocalizeException(
                        f"Storage saved {name} as {saved_name}; relative references would break."
                    )
                r.file.name = saved_name
        finally:
            for tmp in tmp_files.values():
                tmp.close()

        with transaction.atomic():
            for r in external:
                r.external_url = None
                r.save()
            # The archive is also externally hosted; once every resource is
            # local, downloads can be served from our own storage instead.
            if self.zip_archive_url and all(r.file for r in resources):
                self.zip_archive_url = None
                self.save()

        # is_cors_allowed values are cached with no expiry.
        cors_allow_list = get_cached_cors_allow_list()
        resource_pks = "-".join([str(x.pk) for x in self.get_all_resources()])
        cache.delete_many(
            [f"resource_is_cors_allowed-{r.pk}-{cors_allow_list}" for r in external]
            + [f"format_is_cors_allowed-{self.pk}-{resource_pks}-{cors_allow_list}"]
        )
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
        resource_pks = "-".join([str(x.pk) for x in resources])
        cache_key = f"format_is_cors_allowed-{self.pk}-{resource_pks}-{cors_allow_list}"

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
