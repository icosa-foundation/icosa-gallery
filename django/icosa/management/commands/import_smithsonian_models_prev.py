import hashlib
import logging
import mimetypes
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile

from icosa.models import (
    ASSET_STATE_COMPLETE,
    PUBLIC,
    Asset,
    AssetOwner,
    Format,
    Resource,
)


logger = logging.getLogger(__name__)


SUPPORTED_MODEL_TYPES = {"glb", "gltf", "obj", "stl"}
IMPORT_SOURCE = "smithsonian"
API_URL = "https://3d-api.si.edu/api/v1.0/content/file/search"


DEFAULT_OWNER = {
    "url": "smithsonian",
    "displayname": "Smithsonian 3D",
}


@dataclass
class SmithsonianResource:
    uri: str
    usage: Optional[str]
    quality: Optional[str]
    model_type: Optional[str]
    file_type: Optional[str]
    extra: Dict[str, object] = field(default_factory=dict)


@dataclass
class SmithsonianAsset:
    title: str
    model_url: str
    model_entries: List[SmithsonianResource] = field(default_factory=list)
    image_entries: List[SmithsonianResource] = field(default_factory=list)
    seen_uris: Set[str] = field(default_factory=set, repr=False)

    def to_metadata(self) -> Dict[str, object]:
        """Return serialisable metadata for storage on the Asset."""

        return {
            "title": self.title,
            "model_url": self.model_url,
            "models": [entry.__dict__ for entry in self.model_entries],
            "images": [entry.__dict__ for entry in self.image_entries],
        }

    def add_entry(self, entry: SmithsonianResource) -> bool:
        """Add an entry to the asset if it hasn't been seen already."""

        uri = entry.uri
        if uri and uri in self.seen_uris:
            return False

        if uri:
            self.seen_uris.add(uri)

        usage = (entry.usage or "").lower()
        if usage.startswith("image"):
            self.image_entries.append(entry)
        else:
            self.model_entries.append(entry)

        return True

    def preferred_model_entry(self) -> Optional[SmithsonianResource]:
        """Return the best candidate to use as the root resource."""

        if not self.model_entries:
            return None

        def sort_key(entry: SmithsonianResource) -> tuple:
            usage_priority = {
                "web3d": 0,
                "app3d": 1,
                "download3d": 2,
            }.get((entry.usage or "").lower(), 3)
            quality_priority_map = {
                "high": 0,
                "medium": 1,
                "ar": 2,
                "low": 3,
                "full_resolution": 4,
                "thumb": 5,
            }
            quality_priority = quality_priority_map.get((entry.quality or "").lower(), 6)
            # When priorities match, prefer longer urls (heuristic for higher fidelity variants).
            return (usage_priority, quality_priority, -(len(entry.uri) if entry.uri else 0))

        return sorted(self.model_entries, key=sort_key)[0]

    def preferred_image_entry(self) -> Optional[SmithsonianResource]:
        """Return the best candidate thumbnail image."""

        if not self.image_entries:
            return None

        def sort_key(entry: SmithsonianResource) -> tuple:
            usage_priority = {
                "image_thumb": 0,
                "image_thumbnail": 0,
                "image_small": 1,
                "image_medium": 2,
                "image_large": 3,
                "image_master": 4,
            }.get((entry.usage or "").lower(), 5)
            quality_priority = {
                "thumb": 0,
                "low": 1,
                "medium": 2,
                "high": 3,
                "full_resolution": 4,
            }.get((entry.quality or "").lower(), 5)
            return (usage_priority, quality_priority, -(len(entry.uri) if entry.uri else 0))

        return sorted(self.image_entries, key=sort_key)[0]


class SmithsonianAPIClient:
    def __init__(self, model_type: str, rate_limit: float = 0.5, rows_per_page: int = 100):
        self.model_type = model_type
        self.rate_limit = rate_limit
        self.rows_per_page = rows_per_page
        self.session = requests.Session()

    def fetch(self) -> Iterable[List[Dict[str, object]]]:
        start = 0
        total = None

        while True:
            params = {
                "model_type": self.model_type,
                "start": start,
                "rows": self.rows_per_page,
            }
            response = self.session.get(API_URL, params=params, timeout=60)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:  # pragma: no cover - defensive.
                raise CommandError(f"Failed to fetch Smithsonian data: {exc}") from exc

            payload = response.json()
            rows = payload.get("rows", [])
            total = payload.get("rowCount", total)
            logger.info("Fetched %s rows at offset %s", len(rows), start)

            yield rows

            start += self.rows_per_page
            if total is not None and start >= total:
                break

            if not rows:
                break

            time.sleep(self.rate_limit)

    def fetch_by_model_url(self, model_url: str) -> List[Dict[str, object]]:
        start = 0
        collected: List[Dict[str, object]] = []

        while True:
            params = {
                "model_url": model_url,
                "start": start,
                "rows": self.rows_per_page,
            }
            response = self.session.get(API_URL, params=params, timeout=60)
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:  # pragma: no cover - defensive.
                raise CommandError(
                    f"Failed to fetch additional Smithsonian data for {model_url}: {exc}"
                ) from exc

            payload = response.json()
            rows = payload.get("rows", [])
            collected.extend(rows)

            if len(rows) < self.rows_per_page or not rows:
                break

            start += self.rows_per_page
            time.sleep(self.rate_limit)

        return collected


class Command(BaseCommand):
    help = "Import Smithsonian 3D models of a given format into Icosa"

    def add_arguments(self, parser):
        parser.add_argument(
            "--model-type",
            choices=sorted(SUPPORTED_MODEL_TYPES),
            required=True,
            help="Smithsonian model_type filter to import",
        )
        parser.add_argument(
            "--rows",
            type=int,
            default=100,
            help="Number of rows to fetch per API call",
        )
        parser.add_argument(
            "--rate-limit",
            type=float,
            default=0.5,
            help="Seconds to wait between API requests",
        )
        parser.add_argument(
            "--max-assets",
            type=int,
            default=None,
            help="Optional limit on the number of assets to import",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch data but do not write to the database",
        )

    @staticmethod
    def normalise_metadata(rows: Iterable[Dict[str, object]]) -> Dict[str, SmithsonianAsset]:
        assets: Dict[str, SmithsonianAsset] = {}
        for row in rows:
            content = row.get("content", {})
            if not isinstance(content, dict):
                continue
            entry = Command.resource_from_content(content)
            if entry is None:
                continue

            model_url = content.get("model_url")
            if not model_url:
                continue

            title = row.get("title") or "Untitled Smithsonian Model"

            asset = assets.setdefault(
                model_url,
                SmithsonianAsset(title=title, model_url=model_url),
            )

            if entry.uri:
                asset.add_entry(entry)

        return assets

    @staticmethod
    def resource_from_content(content: Dict[str, object]) -> Optional[SmithsonianResource]:
        uri = content.get("uri")
        if not uri:
            return None

        return SmithsonianResource(
            uri=uri,
            usage=content.get("usage"),
            quality=content.get("quality"),
            model_type=content.get("model_type"),
            file_type=content.get("file_type"),
            extra={
                key: value
                for key, value in content.items()
                if key
                not in {"uri", "usage", "quality", "model_type", "file_type", "model_url"}
            },
        )

    @staticmethod
    def guess_content_type(uri: str, default: Optional[str] = None) -> Optional[str]:
        content_type, _ = mimetypes.guess_type(uri)
        if content_type:
            return content_type
        return default

    @staticmethod
    def ensure_owner() -> AssetOwner:
        owner, _ = AssetOwner.objects.get_or_create(
            url=DEFAULT_OWNER["url"],
            defaults={
                "displayname": DEFAULT_OWNER["displayname"],
                "imported": True,
                "is_claimed": False,
            },
        )
        return owner

    @staticmethod
    def asset_identifier(model_url: str) -> str:
        safe_url = model_url.replace(":", "-")
        return f"smithsonian-{safe_url}"

    @staticmethod
    def determine_format_type(model_type: Optional[str], default_model_type: str) -> str:
        model_choice = (model_type or default_model_type or "").lower()
        if model_choice in {"glb", "gltf"}:
            return "GLTF2"
        if not model_choice:
            return "UNKNOWN"
        return model_choice.upper()

    @classmethod
    def determine_content_type(cls, uri: str, format_type: str) -> Optional[str]:
        guessed = cls.guess_content_type(uri)
        if guessed:
            return guessed

        extension = os.path.splitext(urlparse(uri).path)[1].lower()
        if extension == ".glb":
            return "model/gltf-binary"
        if extension == ".gltf":
            return "model/gltf+json"
        if extension == ".obj":
            return "text/plain"
        if extension == ".stl":
            return "model/stl"

        if format_type == "GLTF2":
            return "model/gltf-binary"
        if format_type == "OBJ":
            return "text/plain"
        if format_type == "STL":
            return "model/stl"

        return "application/octet-stream"

    @staticmethod
    def build_format_role(format_type: str, entry: SmithsonianResource, index: int) -> str:
        parts = [format_type]
        if entry.usage:
            parts.append(entry.usage.upper().replace("-", "_").replace(" ", "_"))
        if entry.quality:
            parts.append(entry.quality.upper().replace("-", "_").replace(" ", "_"))
        parts.append(str(index))
        role = "SMITHSONIAN_" + "_".join(filter(None, parts))
        return role[:255]

    def download_thumbnail(
        self, entry: SmithsonianResource
    ) -> Tuple[Optional[ContentFile], Optional[str], int, str]:
        if not entry.uri:
            return None, None, 0, "no URI provided"

        try:
            response = requests.get(entry.uri, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network failure handling
            logger.warning("Failed to download thumbnail %s: %s", entry.uri, exc)
            return None, None, 0, f"request error: {exc}"

        raw_content_type = response.headers.get("Content-Type")
        if raw_content_type:
            raw_content_type = raw_content_type.split(";")[0].strip()

        extension = None
        if raw_content_type:
            extension = mimetypes.guess_extension(raw_content_type)
        if not extension:
            extension = os.path.splitext(urlparse(entry.uri).path)[1]
        if not extension:
            extension = ".jpg"
        if extension == ".jpe":
            extension = ".jpg"

        content_type = raw_content_type or mimetypes.guess_type(f"thumbnail{extension}")[0]

        filename = f"thumbnail-{hashlib.sha256(entry.uri.encode('utf-8')).hexdigest()[:12]}{extension}"
        size = len(response.content)
        diagnostics = (
            f"status={response.status_code}, bytes={size}, "
            f"content_type={content_type or 'unknown'}, extension={extension}"
        )
        logger.debug("Downloaded %s bytes for thumbnail %s", size, entry.uri)
        return ContentFile(response.content, name=filename), content_type, size, diagnostics

    def find_existing_asset(self, asset_data: SmithsonianAsset) -> Optional[Asset]:
        asset_url = self.asset_identifier(asset_data.model_url)
        asset = Asset.objects.filter(url=asset_url).first()
        if asset:
            return asset

        asset = Asset.objects.filter(polydata__model_url=asset_data.model_url).first()
        if asset:
            return asset

        model_uris = [entry.uri for entry in asset_data.model_entries if entry.uri]
        if model_uris:
            resource = (
                Resource.objects.filter(external_url__in=model_uris)
                .select_related("asset")
                .first()
            )
            if resource:
                return resource.asset

        return None

    def create_or_update_asset(
        self,
        asset_data: SmithsonianAsset,
        owner: AssetOwner,
        requested_model_type: str,
        *,
        verbosity: int = 1,
    ) -> Asset:
        root_entry = asset_data.preferred_model_entry()
        if root_entry is None:
            raise CommandError(f"No usable model files found for {asset_data.model_url}")

        asset_url = self.asset_identifier(asset_data.model_url)
        asset = self.find_existing_asset(asset_data)
        created = False

        if asset is None:
            created = True
            asset = Asset(url=asset_url)

        now = timezone.now()
        if created and not asset.create_time:
            asset.create_time = now
        asset.url = asset_url
        asset.name = asset_data.title
        asset.update_time = now
        asset.visibility = PUBLIC
        asset.state = ASSET_STATE_COMPLETE
        asset.owner = owner
        asset.imported_from = IMPORT_SOURCE
        asset.polydata = asset_data.to_metadata()

        if verbosity >= 1:
            action = "Creating" if created else "Updating"
            self.stdout.write(f"{action} asset for Smithsonian model {asset_data.model_url}")

        asset.save()

        thumbnail_entry = asset_data.preferred_image_entry()
        if thumbnail_entry:
            if verbosity >= 1:
                self.stdout.write(f"Attempting thumbnail download from {thumbnail_entry.uri}")
            file_obj, content_type, size, diagnostics = self.download_thumbnail(thumbnail_entry)
            if file_obj:
                asset.thumbnail.save(file_obj.name, file_obj, save=False)
                asset.thumbnail_contenttype = content_type
                if verbosity >= 1:
                    self.stdout.write(
                        f"Saved thumbnail {file_obj.name} ({size} bytes, content_type={content_type or 'unknown'}); {diagnostics}"
                    )
            else:
                if verbosity >= 1:
                    self.stdout.write(
                        f"Failed to download thumbnail from {thumbnail_entry.uri}; {diagnostics}"
                    )
        else:
            image_usages = sorted({(entry.usage or "unknown") for entry in asset_data.image_entries})
            model_usages = sorted({(entry.usage or "unknown") for entry in asset_data.model_entries})
            self.stdout.write(
                "No thumbnail entries available for "
                f"{asset_data.model_url}; image_usages={image_usages or ['none']}, "
                f"model_usages={model_usages or ['none']}"
            )

        with transaction.atomic():
            asset.format_set.filter(role__startswith="SMITHSONIAN_").delete()

            created_formats: List[Tuple[SmithsonianResource, Format]] = []
            for index, entry in enumerate(asset_data.model_entries, start=1):
                entry_format_type = self.determine_format_type(entry.model_type, requested_model_type)
                format_role = self.build_format_role(entry_format_type, entry, index)
                format_obj = Format.objects.create(
                    asset=asset,
                    format_type=entry_format_type,
                    role=format_role,
                )

                resource = Resource.objects.create(
                    asset=asset,
                    format=format_obj,
                    external_url=entry.uri,
                    contenttype=self.determine_content_type(entry.uri, entry_format_type),
                )
                format_obj.add_root_resource(resource)
                created_formats.append((entry, format_obj))

            preferred_format = next((fmt for entry, fmt in created_formats if entry is root_entry), None)

            if preferred_format:
                preferred_format.is_preferred_for_gallery_viewer = True
                preferred_format.save(update_fields=["is_preferred_for_gallery_viewer"])
                asset.preferred_viewer_format_override = preferred_format
                asset.is_viewer_compatible = True
            else:
                asset.preferred_viewer_format_override = None
                asset.is_viewer_compatible = False

        asset.update_time = timezone.now()
        asset.save()

        return asset

    def handle(self, *args, **options):
        model_type = options["model_type"].lower()
        if model_type not in SUPPORTED_MODEL_TYPES:
            raise CommandError(f"Unsupported model type: {model_type}")

        rows = options["rows"]
        rate_limit = options["rate_limit"]
        max_assets = options["max_assets"]
        dry_run = options["dry_run"]
        verbosity = options.get("verbosity", 1)

        client = SmithsonianAPIClient(model_type=model_type, rate_limit=rate_limit, rows_per_page=rows)
        owner = self.ensure_owner()

        imported = 0

        aggregated_assets: Dict[str, SmithsonianAsset] = {}
        usable_asset_count = 0
        stop_fetching = False

        for page_rows in client.fetch():
            for model_url, asset_data in self.normalise_metadata(page_rows).items():
                existing = aggregated_assets.get(model_url)
                if existing:
                    had_models = bool(existing.model_entries)
                    if asset_data.title and asset_data.title != existing.title:
                        existing.title = asset_data.title
                    for entry in asset_data.model_entries:
                        existing.add_entry(entry)
                    for entry in asset_data.image_entries:
                        existing.add_entry(entry)
                    if not had_models and existing.model_entries:
                        usable_asset_count += 1
                else:
                    aggregated_assets[model_url] = asset_data
                    if asset_data.model_entries:
                        usable_asset_count += 1

                if max_assets is not None and usable_asset_count >= max_assets:
                    stop_fetching = True
                    break

            if stop_fetching:
                break

        self.populate_missing_image_entries(client, aggregated_assets, verbosity)

        for asset_data in aggregated_assets.values():
            if not asset_data.model_entries:
                if verbosity >= 2:
                    self.stdout.write(
                        f"Skipping {asset_data.model_url} because it has no usable model entries"
                    )
                continue

            if dry_run:
                self.stdout.write(f"Would import {asset_data.model_url}")
            else:
                self.create_or_update_asset(
                    asset_data,
                    owner,
                    model_type,
                    verbosity=verbosity,
                )
                imported += 1
                self.stdout.write(f"Imported {asset_data.model_url}")

                if max_assets is not None and imported >= max_assets:
                    self.stdout.write("Reached asset import limit")
                    break

        if imported == 0 and not dry_run:
            self.stdout.write("No assets imported")

    def populate_missing_image_entries(
        self,
        client: SmithsonianAPIClient,
        assets: Dict[str, SmithsonianAsset],
        verbosity: int,
    ) -> None:
        for asset in assets.values():
            if asset.image_entries:
                continue

            supplementary_rows = client.fetch_by_model_url(asset.model_url)
            added = 0
            supplementary_usages = set()
            for row in supplementary_rows:
                content = row.get("content", {})
                if not isinstance(content, dict):
                    continue
                usage = content.get("usage")
                if usage:
                    supplementary_usages.add(usage)
                entry = self.resource_from_content(content)
                if entry is None or not entry.uri:
                    continue
                if asset.add_entry(entry):
                    added += 1

            if verbosity >= 2:
                supplementary_usage_list = sorted(supplementary_usages or {"none"})
                self.stdout.write(
                    f"Supplementary fetch for {asset.model_url} returned "
                    f"{len(supplementary_rows)} rows; added {added} new entries; "
                    f"usages={supplementary_usage_list}"
                )
            if not asset.image_entries and supplementary_rows:
                model_usages = sorted({(entry.usage or "unknown") for entry in asset.model_entries})
                supplementary_usage_list = sorted(supplementary_usages or {"none"})
                self.stdout.write(
                    "No image entries found for "
                    f"{asset.model_url} after supplementary fetch; "
                    f"supplementary_usages={supplementary_usage_list}, "
                    f"model_usages={model_usages or ['none']}"
                )

