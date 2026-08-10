from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from constance import config
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from icosa.helpers.snowflake import generate_snowflake
from icosa.models import (
    ASSET_STATE_COMPLETE,
    PUBLIC,
    Asset,
    AssetOwner,
    Format,
    Resource,
    Tag,
)

API_URL = "https://api.icosa.gallery/v1/assets"
IMPORT_SOURCE = "api.icosa.gallery"
SEED_COUNT = 20
REQUEST_TIMEOUT = 30


class Command(BaseCommand):
    help = "Seed the local database with the first 20 assets from api.icosa.gallery."

    def handle(self, *args, **options):
        session = requests.Session()
        session.headers["User-Agent"] = "Icosa-Gallery-Development-Seeder/1.0"

        try:
            response = session.get(
                API_URL,
                params={"pageSize": SEED_COUNT, "pageToken": 1},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CommandError(f"Could not fetch seed assets: {exc}") from exc

        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise CommandError("The Icosa Gallery API response did not contain an assets list.")

        assets = assets[:SEED_COUNT]
        self._allow_upstream_media_hosts(assets)

        created = 0
        skipped = 0
        for asset_data in assets:
            asset_id = asset_data.get("assetId")
            if not asset_id:
                self.stderr.write(self.style.WARNING("Skipped an asset without an assetId."))
                skipped += 1
                continue
            if Asset.objects.filter(url=asset_id).exists():
                self.stdout.write(f"Skipping existing asset {asset_id}.")
                skipped += 1
                continue

            try:
                with transaction.atomic():
                    self._create_asset(session, asset_data)
            except (requests.RequestException, ValueError) as exc:
                raise CommandError(f"Could not import asset {asset_id}: {exc}") from exc

            self.stdout.write(self.style.SUCCESS(f"Imported {asset_id}."))
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {created} imported, {skipped} skipped."
            )
        )

    def _create_asset(self, session, data):
        asset_id = data["assetId"]
        owner_id = data.get("authorId") or f"seed-owner-{asset_id}"
        owner, _ = AssetOwner.objects.get_or_create(
            url=owner_id,
            defaults={
                "displayname": data.get("authorName") or "Unknown artist",
                "imported": True,
                "is_claimed": False,
            },
        )

        create_time = parse_datetime(data.get("createTime", ""))
        if create_time is None:
            raise ValueError("createTime is missing or invalid")

        asset = Asset(
            id=generate_snowflake(),
            url=asset_id,
            name=data.get("displayName") or asset_id,
            owner=owner,
            description=data.get("description"),
            visibility=data.get("visibility", PUBLIC),
            curated=bool(data.get("isCurated", False)),
            create_time=create_time,
            update_time=parse_datetime(data.get("updateTime") or ""),
            license=self._local_license(data),
            presentation_params=data.get("presentationParams"),
            imported_from=IMPORT_SOURCE,
            state=ASSET_STATE_COMPLETE,
            triangle_count=data.get("triangleCount") or 0,
            is_viewer_compatible=bool(data.get("isIcosaGalleryCompatible", False)),
        )
        asset.save(bypass_custom_logic=True, bypass_moderation_logging=True)

        tags = [Tag.objects.get_or_create(name=name)[0] for name in data.get("tags", [])]
        asset.tags.set(tags)

        for format_data in data.get("formats", []):
            self._create_format(asset, format_data)

        thumbnail = data.get("thumbnail") or {}
        if thumbnail.get("url"):
            self._download_thumbnail(session, asset, thumbnail)

        asset.update_search_text()
        asset.denorm_format_types()
        asset.denorm_triangle_count()
        asset.denorm_tags()
        asset.rank = asset.get_updated_rank()
        asset.save(bypass_custom_logic=True, bypass_moderation_logging=True)

    def _create_format(self, asset, data):
        complexity = data.get("formatComplexity") or {}
        asset_format = Format.objects.create(
            asset=asset,
            format_type=data.get("formatType") or "UNKNOWN",
            zip_archive_url=data.get("zip_archive_url"),
            triangle_count=complexity.get("triangleCount"),
            lod_hint=complexity.get("lodHint"),
            role=data.get("role"),
            is_preferred_for_download=bool(data.get("isPreferredForDownload", True)),
            is_preferred_for_gallery_viewer=bool(
                data.get("isPreferredForGalleryViewer", False)
            ),
        )

        root_data = data.get("root")
        if root_data and root_data.get("url"):
            root = self._create_resource(asset, root_data)
            asset_format.root_resource = root
            asset_format.save(update_fields=["root_resource"])

        for resource_data in data.get("resources") or []:
            if resource_data.get("url"):
                self._create_resource(asset, resource_data, asset_format)

    @staticmethod
    def _create_resource(asset, data, asset_format=None):
        return Resource.objects.create(
            asset=asset,
            format=asset_format,
            external_url=data["url"],
            contenttype=data.get("contentType") or "application/octet-stream",
        )

    @staticmethod
    def _download_thumbnail(session, asset, data):
        response = session.get(data["url"], timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        filename = data.get("relativePath") or Path(
            unquote(urlparse(data["url"]).path)
        ).name
        filename = Path(filename).name or f"{asset.url}.png"
        asset.thumbnail.save(filename, ContentFile(response.content), save=False)
        asset.thumbnail_contenttype = data.get("contentType") or response.headers.get(
            "Content-Type"
        )

    @staticmethod
    def _local_license(data):
        license_name = data.get("license")
        version = data.get("licenseVersion")
        if license_name == "CC0":
            return "CREATIVE_COMMONS_0"
        if license_name in {"CREATIVE_COMMONS_BY", "CREATIVE_COMMONS_BY_ND"} and version:
            return f"{license_name}_{version.replace('.', '_')}"
        return license_name

    @staticmethod
    def _allow_upstream_media_hosts(assets):
        hosts = {
            urlparse(resource["url"]).netloc
            for asset in assets
            for asset_format in asset.get("formats", [])
            if asset_format.get("isCorsAllowed")
            for resource in [asset_format.get("root"), *(asset_format.get("resources") or [])]
            if resource and resource.get("url")
        }
        existing_hosts = {
            host.strip()
            for host in config.EXTERNAL_MEDIA_CORS_ALLOW_LIST.split(",")
            if host.strip()
        }
        if hosts - existing_hosts:
            config.EXTERNAL_MEDIA_CORS_ALLOW_LIST = ",".join(
                sorted(existing_hosts | hosts)
            )
