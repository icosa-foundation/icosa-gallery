import os
import posixpath
import tempfile
from contextlib import closing
from urllib.parse import parse_qs, unquote, urlparse

import requests
from constance import config
from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from icosa.api.filters import FiltersAsset, FiltersOrder, filter_and_sort_assets
from icosa.model_mixins import MOD_HIDDEN
from icosa.models import ALL_RIGHTS_RESERVED, PUBLIC, Asset
from icosa.models.helpers import get_cloud_media_root


ARCHIVE_HOSTS = ("archive.org", "web.archive.org")


def is_archive_url(url):
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return host in ARCHIVE_HOSTS or host.endswith(".archive.org")


def get_original_url(url):
    parsed = urlparse(url)
    if parsed.netloc.lower() != "web.archive.org":
        return url

    marker = "/web/"
    if not parsed.path.startswith(marker):
        return url

    archived_path = parsed.path[len(marker) :]
    if archived_path.startswith(("http://", "https://")):
        return unquote(archived_path)

    _, _, original_url = archived_path.partition("/")
    return unquote(original_url) if original_url else url


def get_source_path(url):
    original_url = get_original_url(url)
    path = unquote(urlparse(original_url).path).lstrip("/")
    return path or posixpath.basename(urlparse(url).path)


def get_resource_filename(resource, format_obj=None):
    format_obj = format_obj or resource.format
    source_path = get_source_path(resource.external_url)
    filename = posixpath.basename(source_path)
    if resource.format is None:
        _, ext = os.path.splitext(filename)
        return f"model{ext}"
    if filename.lower().endswith(".obj") and format_obj.role == "ORIGINAL_TRIANGULATED_OBJ_FORMAT":
        return "model-triangulated.obj"
    return filename


def get_common_source_dir(resources):
    dirs = []
    for resource in resources:
        if not resource.external_url:
            continue
        path = get_source_path(resource.external_url)
        directory = posixpath.dirname(path)
        if directory:
            dirs.append(directory)
    return posixpath.commonpath(dirs) if dirs else ""


def get_storage_name(resource, common_source_dir, format_obj=None):
    format_obj = format_obj or resource.format or resource.root_formats.first()
    if format_obj is None:
        raise CommandError(f"Resource {resource.pk} is not attached to a format.")

    source_path = get_source_path(resource.external_url)
    source_dir = posixpath.dirname(source_path)
    relative_dir = ""
    if common_source_dir and source_dir:
        relative_dir = posixpath.relpath(source_dir, common_source_dir)
        if relative_dir == ".":
            relative_dir = ""

    parts = [
        get_cloud_media_root().strip("/"),
        str(resource.asset.owner.id),
        str(resource.asset.id),
        format_obj.format_type,
        relative_dir,
        get_resource_filename(resource, format_obj),
    ]
    return "/".join(part.strip("/") for part in parts if part)


def parse_api_query(query_string):
    query_string = query_string.lstrip("?")
    parsed = parse_qs(query_string, keep_blank_values=False)
    values = {}
    for key, value in parsed.items():
        if key in ["format", "tag"]:
            expanded_values = []
            for item in value:
                expanded_values.extend([part for part in item.split(",") if part])
            values[key] = expanded_values
        else:
            values[key] = value[-1] if value else None
    for pagination_key in ["limit", "offset", "page", "per_page"]:
        values.pop(pagination_key, None)
    return values


def get_format_resources(format_obj):
    resources = []
    if format_obj.root_resource is not None:
        resources.append(format_obj.root_resource)
    resources.extend(format_obj.resource_set.all())
    return resources


class Command(BaseCommand):
    help = (
        "Copies archive.org-hosted resources for a selected API asset query "
        "and format type into Django storage/B2."
    )

    def add_arguments(self, parser):
        parser.add_argument("--format", required=True, dest="format_type", help="Format.format_type to copy.")
        parser.add_argument(
            "--query",
            default="",
            help="Raw /v1/assets query string, for example 'orderBy=BEST&category=ART'.",
        )
        parser.add_argument("--limit", type=int, default=None, help="Maximum number of assets to process.")
        parser.add_argument("--dry-run", action="store_true", help="Print intended changes without uploading.")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Download and store a resource even when its destination key already exists.",
        )
        parser.add_argument(
            "--keep-external-url",
            action="store_true",
            help="Leave Resource.external_url populated after the local file is saved.",
        )
        parser.add_argument(
            "--allow-local-storage",
            action="store_true",
            help="Allow the command to run when Django is configured for local filesystem media.",
        )
        parser.add_argument("--timeout", type=int, default=120, help="Per-request timeout in seconds.")
        parser.add_argument("--chunk-size", type=int, default=1024 * 1024, help="Download chunk size in bytes.")

    def handle(self, *args, **options):
        if settings.LOCAL_MEDIA_STORAGE and not options["allow_local_storage"]:
            raise CommandError(
                "Django is configured for local media storage. Set B2 storage env vars or pass --allow-local-storage."
            )

        assets = self.get_assets(options)
        total_assets = assets.count()
        if options["limit"] is not None:
            assets = assets[: options["limit"]]

        self.stdout.write(
            f"ARCHIVE_TO_B2 format={options['format_type']} assets={total_assets}"
        )

        copied = 0
        skipped = 0
        failed = 0

        for asset in assets:
            formats = asset.format_set.filter(format_type=options["format_type"]).select_related("root_resource")
            for format_obj in formats:
                try:
                    result = self.copy_format(format_obj, options)
                except Exception as err:
                    failed += 1
                    self.stderr.write(f"ARCHIVE_TO_B2 failed asset={asset.url} format={format_obj.pk}: {err}")
                    continue

                copied += result["copied"]
                skipped += result["skipped"]
                if result["changed"] and not options["dry_run"]:
                    asset.save()

        self.stdout.write(f"ARCHIVE_TO_B2 done copied={copied} skipped={skipped} failed={failed}")

    def get_assets(self, options):
        query_values = parse_api_query(options["query"])
        order_values = {}
        for key in ["orderBy", "order_by"]:
            if key in query_values:
                order_values[key] = query_values.pop(key)

        filters = FiltersAsset(**query_values)
        order = FiltersOrder(**order_values)

        exc_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED)
        if config.HIDE_REPORTED_ASSETS:
            exc_q |= Q(moderation_state__in=MOD_HIDDEN)

        return filter_and_sort_assets(
            filters,
            order,
            assets=Asset.objects.filter(visibility=PUBLIC),
            exc_q=exc_q,
        )

    def copy_format(self, format_obj, options):
        resources = get_format_resources(format_obj)
        if not resources:
            self.stdout.write(f"ARCHIVE_TO_B2 skip format={format_obj.pk} reason=no-resources")
            return {"copied": 0, "skipped": 1, "changed": False}

        common_source_dir = get_common_source_dir(resources)
        changed = False
        copied = 0
        skipped = 0
        updates = []

        for resource in resources:
            if resource.file and not options["overwrite"]:
                skipped += 1
                self.stdout.write(f"ARCHIVE_TO_B2 skip resource={resource.pk} reason=already-has-file")
                continue

            if not is_archive_url(resource.external_url):
                self.stdout.write(f"ARCHIVE_TO_B2 skip format={format_obj.pk} reason=missing-archive-url")
                return {"copied": 0, "skipped": 1, "changed": False}

            storage_name = get_storage_name(resource, common_source_dir, format_obj)

            if options["dry_run"]:
                copied += 1
                self.stdout.write(
                    f"ARCHIVE_TO_B2 dry-run resource={resource.pk} url={resource.external_url} -> {storage_name}"
                )
                continue

            if default_storage.exists(storage_name) and not options["overwrite"]:
                updates.append((resource, storage_name))
                skipped += 1
                self.stdout.write(f"ARCHIVE_TO_B2 attach-existing resource={resource.pk} file={storage_name}")
                continue

            saved_name = self.download_to_storage(resource.external_url, storage_name, options)
            updates.append((resource, saved_name))
            copied += 1
            self.stdout.write(f"ARCHIVE_TO_B2 copied resource={resource.pk} file={saved_name}")

        for resource, saved_name in updates:
            resource.file.name = saved_name
            if not options["keep_external_url"]:
                resource.external_url = None
            resource.save()
            changed = True

        all_resources_have_files = all(resource.file for resource in resources)
        if (changed or all_resources_have_files) and format_obj.zip_archive_url and not options["dry_run"]:
            format_obj.zip_archive_url = None
            format_obj.save()
            changed = True

        return {"copied": copied, "skipped": skipped, "changed": changed}

    def download_to_storage(self, url, storage_name, options):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, "download")
            with closing(requests.get(url, stream=True, timeout=options["timeout"])) as response:
                response.raise_for_status()
                with open(temp_path, "wb") as temp_file:
                    for chunk in response.iter_content(chunk_size=options["chunk_size"]):
                        if chunk:
                            temp_file.write(chunk)

            if options["overwrite"] and default_storage.exists(storage_name):
                default_storage.delete(storage_name)

            with open(temp_path, "rb") as temp_file:
                return default_storage.save(storage_name, File(temp_file))
