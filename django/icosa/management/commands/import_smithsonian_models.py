import hashlib
import io
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
from PIL import Image

from icosa.models import (
    ASSET_STATE_COMPLETE,
    PUBLIC,
    Asset,
    AssetOwner,
    Format,
    Resource,
    Tag,
)


logger = logging.getLogger(__name__)


SUPPORTED_FILE_TYPES: Tuple[str, ...] = ("glb", "gltf", "obj", "stl")
SUPPORTED_FILE_TYPE_SET = set(SUPPORTED_FILE_TYPES)
IMPORT_SOURCE = "smithsonian"
API_URL = "https://3d-api.si.edu/api/v1.0/content/file/search"
OPEN_ACCESS_API_URL = "https://api.si.edu/openaccess/api/v1.0/search"
DEFAULT_API_KEY = "DEMO_KEY"  # Can be overridden with --api-key


DEFAULT_OWNER = {
    "url": "smithsonian",
    "displayname": "Smithsonian 3D"
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
    record_id: Optional[str] = None
    record_link: Optional[str] = None
    unit_code: Optional[str] = None
    object_name: Optional[str] = None
    description: Optional[str] = None
    license: Optional[str] = None
    credit: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    additional_metadata: Dict[str, object] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, object]:
        """Return serialisable metadata for storage on the Asset."""

        metadata = {
            "title": self.title,
            "model_url": self.model_url,
            "models": [entry.__dict__ for entry in self.model_entries],
            "images": [entry.__dict__ for entry in self.image_entries],
        }

        # Add rich metadata fields if present
        if self.record_id:
            metadata["record_id"] = self.record_id
        if self.record_link:
            metadata["record_link"] = self.record_link
        if self.unit_code:
            metadata["unit_code"] = self.unit_code
        if self.object_name:
            metadata["object_name"] = self.object_name
        if self.description:
            metadata["description"] = self.description
        if self.license:
            metadata["license"] = self.license
        if self.credit:
            metadata["credit"] = self.credit
        if self.additional_metadata:
            metadata["additional_metadata"] = self.additional_metadata

        return metadata

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
    def __init__(
        self,
        file_types: Iterable[str],
        rate_limit: float = 0.5,
        rows_per_page: int = 100,
        api_key: str = DEFAULT_API_KEY,
    ):
        self.file_types = list(dict.fromkeys(file_type.lower() for file_type in file_types))
        self.rate_limit = rate_limit
        self.rows_per_page = rows_per_page
        self.api_key = api_key
        self.session = requests.Session()

    def fetch(self) -> Iterable[List[Dict[str, object]]]:
        for file_type in self.file_types:
            start = 0
            total = None

            while True:
                params = {
                    "file_type": file_type,
                    "start": start,
                    "rows": self.rows_per_page,
                }
                response = self.session.get(API_URL, params=params, timeout=60)
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:  # pragma: no cover - defensive.
                    raise CommandError(
                        f"Failed to fetch Smithsonian data for file_type={file_type}: {exc}"
                    ) from exc

                payload = response.json()
                rows = payload.get("rows", [])
                total = payload.get("rowCount", total)
                logger.info(
                    "Fetched %s rows for file_type=%s at offset %s", len(rows), file_type, start
                )

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

    def fetch_open_access_metadata(self, model_url: str) -> Optional[Dict[str, object]]:
        """Fetch rich metadata from the Smithsonian Open Access API for a 3D package."""
        try:
            params = {
                "q": model_url,
                "api_key": self.api_key,
                "rows": 1,
            }
            response = self.session.get(OPEN_ACCESS_API_URL, params=params, timeout=60)
            response.raise_for_status()

            payload = response.json()
            rows = payload.get("response", {}).get("rows", [])

            if rows:
                return rows[0]
            return None

        except requests.RequestException as exc:
            logger.warning("Failed to fetch Open Access metadata for %s: %s", model_url, exc)
            return None


class Command(BaseCommand):
    help = "Import Smithsonian 3D models into Icosa"

    # Mapping of Smithsonian unit codes to our categories
    UNIT_CODE_CATEGORY_MAP = {
        "nasm": "TRANSPORT",  # National Air and Space Museum
        "nmah": "HISTORY",  # National Museum of American History
        "nmnh": "NATURE",  # National Museum of Natural History
        "nmnhmammals": "ANIMALS",  # NMNH - Mammals
        "nmnhbirds": "ANIMALS",  # NMNH - Birds
        "nmnhfishes": "ANIMALS",  # NMNH - Fishes
        "nmnhreptiles": "ANIMALS",  # NMNH - Reptiles
        "nmnhamphibians": "ANIMALS",  # NMNH - Amphibians
        "nmnhinvertebratezoo": "ANIMALS",  # NMNH - Invertebrate Zoology
        "nmnhanthro": "CULTURE",  # NMNH - Anthropology
        "nmnhbotany": "NATURE",  # NMNH - Botany
        "nmnhentomology": "ANIMALS",  # NMNH - Entomology
        "nmnhiz": "ANIMALS",  # NMNH - Invertebrate Zoology
        "nmnhminsci": "SCIENCE",  # NMNH - Mineral Sciences
        "nmnhpaleo": "SCIENCE",  # NMNH - Paleobiology
        "npg": "PEOPLE",  # National Portrait Gallery
        "saam": "ART",  # Smithsonian American Art Museum
        "acm": "CULTURE",  # Anacostia Community Museum
        "fsg": "ART",  # Freer Gallery of Art and Arthur M. Sackler Gallery
        "hmsg": "ART",  # Hirshhorn Museum and Sculpture Garden
        "npm": "HISTORY",  # National Postal Museum
        "chndm": "ART",  # Cooper Hewitt, Smithsonian Design Museum
        "nzp": "ANIMALS",  # National Zoological Park
        "si": "MISCELLANEOUS",  # Smithsonian Institution (general)
        "cfch": "CULTURE",  # Center for Folklife and Cultural Heritage
    }

    def add_arguments(self, parser):
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
        parser.add_argument(
            "--fix-thumbs",
            action="store_true",
            help="Only download missing thumbnails for already-imported assets",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing assets with fresh metadata (default: skip existing)",
        )
        parser.add_argument(
            "--api-key",
            type=str,
            default=DEFAULT_API_KEY,
            help=f"Smithsonian Open Access API key (default: {DEFAULT_API_KEY})",
        )

    @staticmethod
    def normalise_metadata(rows: Iterable[Dict[str, object]]) -> Dict[str, SmithsonianAsset]:
        """Extract basic file information from 3D API rows. Rich metadata comes from Open Access API."""
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

            asset = assets.get(model_url)
            if asset is None:
                asset = SmithsonianAsset(
                    title=title,
                    model_url=model_url,
                )
                assets[model_url] = asset

            if entry.uri and Command.should_include_entry(entry):
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
    def is_image_usage(usage: Optional[str]) -> bool:
        return (usage or "").lower().startswith("image")

    @classmethod
    def infer_file_type(cls, entry: SmithsonianResource) -> Optional[str]:
        detected = entry.extra.get("detected_file_type")
        if isinstance(detected, str) and detected:
            return detected.lower()

        for candidate in (entry.model_type, entry.file_type):
            if candidate:
                detected_type = candidate.lower()
                entry.extra.setdefault("detected_file_type", detected_type)
                return detected_type

        path = urlparse(entry.uri).path
        extension = os.path.splitext(path)[1].lstrip(".").lower()
        if extension:
            entry.extra.setdefault("detected_file_type", extension)
            return extension

        return None

    @classmethod
    def should_include_entry(cls, entry: SmithsonianResource) -> bool:
        if cls.is_image_usage(entry.usage):
            return True

        detected_type = cls.infer_file_type(entry)
        return bool(detected_type and detected_type in SUPPORTED_FILE_TYPE_SET)

    @staticmethod
    def guess_content_type(uri: str, default: Optional[str] = None) -> Optional[str]:
        content_type, _ = mimetypes.guess_type(uri)
        if content_type:
            return content_type
        return default

    @classmethod
    def extract_unit_code(cls, record_id: Optional[str]) -> Optional[str]:
        """Extract unit code from Smithsonian record ID like 'nasm_A20120325000'."""
        if not record_id:
            return None
        parts = record_id.split("_")
        if len(parts) >= 1:
            return parts[0].lower()
        return None

    @classmethod
    def determine_category(cls, unit_code: Optional[str]) -> Optional[str]:
        """Map Smithsonian unit code to our category."""
        if not unit_code:
            return None

        unit_lower = unit_code.lower()

        # Try exact match first
        category = cls.UNIT_CODE_CATEGORY_MAP.get(unit_lower)
        if category:
            return category

        # Fallback: try prefix matching (e.g., "nmnhsomething" -> "nmnh")
        # Sort by length descending to match longest prefix first
        for prefix in sorted(cls.UNIT_CODE_CATEGORY_MAP.keys(), key=len, reverse=True):
            if unit_lower.startswith(prefix):
                return cls.UNIT_CODE_CATEGORY_MAP[prefix]

        return None

    @classmethod
    def parse_license(cls, license_text: Optional[str]) -> Optional[str]:
        """Convert Smithsonian license text to our license constant."""
        if not license_text:
            return None
        license_lower = license_text.lower()
        if "cc0" in license_lower or "public domain" in license_lower:
            return "CREATIVE_COMMONS_0"
        # Default to None if we can't determine
        return None

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

    @classmethod
    def determine_format_type(cls, entry: SmithsonianResource) -> Optional[str]:
        detected_type = cls.infer_file_type(entry)
        if not detected_type:
            return None

        if detected_type in {"glb", "gltf"}:
            return "GLTF2"
        if detected_type == "obj":
            return "OBJ"
        if detected_type == "stl":
            return "STL"

        return None

    @classmethod
    def determine_content_type(cls, uri: str, format_type: Optional[str]) -> Optional[str]:
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

        raw_size = len(response.content)

        try:
            # Process the image to normalize format and aspect ratio
            with Image.open(io.BytesIO(response.content)) as im:
                # Sample top-left pixel color for background
                bg_color = (255, 255, 255)  # default white
                try:
                    if im.mode in ("RGB", "RGBA", "L", "LA", "P"):
                        pixel = im.getpixel((0, 0))
                        if isinstance(pixel, int):
                            # Grayscale
                            bg_color = (pixel, pixel, pixel)
                        elif len(pixel) >= 3:
                            # RGB or RGBA
                            bg_color = tuple(pixel[:3])
                        elif len(pixel) == 2:
                            # LA (luminance + alpha)
                            bg_color = (pixel[0], pixel[0], pixel[0])
                except Exception:
                    # If sampling fails, stick with white
                    pass

                # Ensure RGB (discard alpha on background color if present)
                if im.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", im.size, bg_color)
                    if im.mode == "P" and "transparency" in im.info:
                        im = im.convert("RGBA")
                    if im.mode in ("RGBA", "LA"):
                        alpha = im.split()[-1]
                        bg.paste(im.convert("RGB"), mask=alpha)
                        im = bg
                    else:
                        bg.paste(im.convert("RGB"))
                        im = bg
                else:
                    im = im.convert("RGB")

                # Fit image into an 8:5 box without upscaling image content
                target_ar = 8 / 5
                max_w, max_h = 1600, 1000  # upper bound for large sources
                w, h = im.size

                # Scale down if larger than max box; never scale up
                scale = min(1.0, min(max_w / w, max_h / h))
                new_w = int(w * scale)
                new_h = int(h * scale)
                if scale < 1.0:
                    im = im.resize((new_w, new_h), Image.LANCZOS)
                else:
                    new_w, new_h = w, h

                # Compute minimal padding to achieve 8:5 aspect ratio canvas
                if new_w / new_h < target_ar:
                    canvas_w = int(round(new_h * target_ar))
                    canvas_h = new_h
                else:
                    canvas_w = new_w
                    canvas_h = int(round(new_w / target_ar))

                # Add 10% padding around the image using sampled background color
                pad = int(0.1 * max(canvas_w, canvas_h))
                padded_w = canvas_w + 2 * pad
                padded_h = canvas_h + 2 * pad
                canvas = Image.new("RGB", (padded_w, padded_h), bg_color)

                # Center the image on the padded canvas
                paste_x = (padded_w - canvas_w) // 2
                paste_y = (padded_h - canvas_h) // 2
                inner_canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
                img_x = (canvas_w - new_w) // 2
                img_y = (canvas_h - new_h) // 2
                inner_canvas.paste(im, (img_x, img_y))
                canvas.paste(inner_canvas, (paste_x, paste_y))

                # Save as JPEG
                buf = io.BytesIO()
                canvas.save(buf, format="JPEG", quality=90)
                buf.seek(0)
                processed_content = buf.read()

                filename = f"thumbnail-{hashlib.sha256(entry.uri.encode('utf-8')).hexdigest()[:12]}.jpg"
                content_type = "image/jpeg"
                size = len(processed_content)
                diagnostics = (
                    f"status={response.status_code}, raw_bytes={raw_size}, "
                    f"processed_bytes={size}, content_type={content_type}, "
                    f"original_size={w}x{h}, final_size={padded_w}x{padded_h}"
                )
                logger.debug("Processed thumbnail %s: %s", entry.uri, diagnostics)
                return ContentFile(processed_content, name=filename), content_type, size, diagnostics

        except Exception as exc:
            logger.warning("Failed to process thumbnail image %s: %s", entry.uri, exc)
            # Fall back to returning raw content if image processing fails
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
            diagnostics = (
                f"status={response.status_code}, bytes={raw_size}, "
                f"content_type={content_type or 'unknown'}, extension={extension}, "
                f"processing_error={exc}"
            )
            return ContentFile(response.content, name=filename), content_type, raw_size, diagnostics

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
        *,
        verbosity: int = 1,
        update_existing: bool = False,
    ) -> Optional[Asset]:
        root_entry = asset_data.preferred_model_entry()
        if root_entry is None:
            raise CommandError(f"No usable model files found for {asset_data.model_url}")

        asset_url = self.asset_identifier(asset_data.model_url)
        asset = self.find_existing_asset(asset_data)
        created = False

        if asset is None:
            created = True
            asset = Asset(url=asset_url)
        else:
            # Asset already exists - skip if update_existing is False
            if not update_existing:
                if verbosity >= 2:
                    self.stdout.write(f"Skipping existing asset {asset_data.model_url}")
                return None

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

        # Set license
        if asset_data.license:
            parsed_license = self.parse_license(asset_data.license)
            if parsed_license:
                asset.license = parsed_license

        # Build description from available metadata
        description_parts = []
        if asset_data.description:
            description_parts.append(asset_data.description)
        if asset_data.credit:
            description_parts.append(f"Credit: {asset_data.credit}")
        if description_parts:
            asset.description = "\n\n".join(description_parts)

        # Determine category from unit code
        if asset_data.unit_code:
            category = self.determine_category(asset_data.unit_code)
            if category:
                asset.category = category
                if verbosity >= 1:
                    self.stdout.write(f"  → Category: {category} (from unit_code: {asset_data.unit_code})")
            else:
                if verbosity >= 1:
                    self.stdout.write(f"  → No category mapping for unit_code: {asset_data.unit_code}")
        else:
            if verbosity >= 1:
                self.stdout.write(f"  → No unit_code found")

        if verbosity >= 1:
            action = "Creating" if created else "Updating"
            self.stdout.write(f"{action} asset for Smithsonian model {asset_data.model_url}")
            if asset_data.license:
                self.stdout.write(f"  → License: {asset_data.license}")
            if asset_data.description:
                desc_preview = asset_data.description[:100] + "..." if len(asset_data.description) > 100 else asset_data.description
                self.stdout.write(f"  → Description: {desc_preview}")

        asset.save()

        # Add tags from Smithsonian metadata
        if asset_data.tags:
            if verbosity >= 2:
                self.stdout.write(f"  → Tags: {', '.join(asset_data.tags)}")

            for tag_name in asset_data.tags:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                asset.tags.add(tag)
        else:
            if verbosity >= 2:
                self.stdout.write(f"  → No tags from metadata")

        # Download thumbnail if asset doesn't have one or if updating existing assets
        if not asset.thumbnail or update_existing:
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
                if verbosity >= 1:
                    self.stdout.write(
                        "No thumbnail entries available for "
                        f"{asset_data.model_url}; image_usages={image_usages or ['none']}, "
                        f"model_usages={model_usages or ['none']}"
                    )
        elif verbosity >= 2:
            self.stdout.write(f"Thumbnail already exists and --update-existing not set, skipping download")

        with transaction.atomic():
            asset.format_set.filter(role__startswith="SMITHSONIAN_").delete()

            created_formats: List[Tuple[SmithsonianResource, Format]] = []
            for index, entry in enumerate(asset_data.model_entries, start=1):
                entry_format_type = self.determine_format_type(entry)
                if entry_format_type is None:
                    if verbosity >= 2:
                        self.stdout.write(
                            "Skipping unsupported Smithsonian resource "
                            f"{entry.uri} for asset {asset_data.model_url}"
                        )
                    continue
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

            if not created_formats:
                raise CommandError(
                    f"No supported Smithsonian formats could be created for {asset_data.model_url}"
                )

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
        rows = options["rows"]
        rate_limit = options["rate_limit"]
        max_assets = options["max_assets"]
        dry_run = options["dry_run"]
        fix_thumbs = options["fix_thumbs"]
        update_existing = options["update_existing"]
        api_key = options["api_key"]
        verbosity = options.get("verbosity", 1)

        client = SmithsonianAPIClient(
            file_types=SUPPORTED_FILE_TYPES,
            rate_limit=rate_limit,
            rows_per_page=rows,
            api_key=api_key,
        )
        owner = self.ensure_owner()

        if fix_thumbs:
            self.fix_missing_thumbnails(client, verbosity, dry_run)
            return

        imported = 0
        skipped = 0

        aggregated_assets: Dict[str, SmithsonianAsset] = {}
        usable_asset_count = 0
        stop_fetching = False

        for page_rows in client.fetch():
            page_assets: Dict[str, SmithsonianAsset] = {}

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
                    page_assets[model_url] = asset_data
                    if asset_data.model_entries:
                        usable_asset_count += 1

            # Process this page's assets immediately
            if page_assets:
                self.populate_missing_image_entries(client, page_assets, verbosity)

                # Filter which assets to enrich and import
                for model_url, asset_data in page_assets.items():
                    if not asset_data.model_entries:
                        if verbosity >= 2:
                            self.stdout.write(
                                f"Skipping {asset_data.model_url} because it has no usable model entries"
                            )
                        continue

                    # Check if we should process this asset
                    should_process = update_existing or self.find_existing_asset(asset_data) is None

                    if not should_process:
                        skipped += 1
                        if verbosity >= 2:
                            self.stdout.write(f"Skipping existing asset {model_url}")
                        continue

                    # Enrich with Open Access metadata
                    if verbosity >= 2:
                        self.stdout.write(f"Enriching {model_url} with Open Access metadata...")
                    oa_record = client.fetch_open_access_metadata(model_url)
                    if oa_record:
                        self.apply_open_access_metadata(asset_data, oa_record, verbosity)
                    else:
                        if verbosity >= 1:
                            self.stdout.write(f"  → No Open Access metadata found for {model_url}")

                    # Write to database immediately
                    if dry_run:
                        self.stdout.write(f"Would import {asset_data.model_url}")
                    else:
                        result = self.create_or_update_asset(
                            asset_data,
                            owner,
                            verbosity=verbosity,
                            update_existing=update_existing,
                        )
                        if result is not None:
                            imported += 1
                            if verbosity >= 1:
                                self.stdout.write(f"Imported {asset_data.model_url}")

                    if max_assets is not None and imported >= max_assets:
                        self.stdout.write("Reached asset import limit")
                        stop_fetching = True
                        break

            if stop_fetching:
                break

        if not dry_run:
            if imported == 0 and skipped == 0:
                self.stdout.write("No assets imported")
            else:
                self.stdout.write(f"Import complete: {imported} imported, {skipped} skipped")

    def fix_missing_thumbnails(
        self,
        client: SmithsonianAPIClient,
        verbosity: int,
        dry_run: bool,
    ) -> None:
        """Download missing thumbnails for already-imported Smithsonian assets."""
        from django.db.models import Q
        from django.conf import settings

        all_smithsonian_assets = Asset.objects.filter(
            imported_from=IMPORT_SOURCE,
        ).select_related("owner")

        # Filter assets that either have no thumbnail path OR the file doesn't exist
        assets_without_thumbs = []
        for asset in all_smithsonian_assets:
            if not asset.thumbnail:
                assets_without_thumbs.append(asset)
            elif settings.LOCAL_MEDIA_STORAGE and hasattr(asset.thumbnail, 'path'):
                # Check if local file exists
                try:
                    if not os.path.exists(asset.thumbnail.path):
                        assets_without_thumbs.append(asset)
                except (ValueError, AttributeError):
                    # thumbnail.path may raise ValueError if file doesn't exist
                    assets_without_thumbs.append(asset)

        total = len(assets_without_thumbs)
        if total == 0:
            self.stdout.write("All Smithsonian assets already have thumbnails")
            return

        self.stdout.write(f"Found {total} Smithsonian assets without thumbnails (or missing files)")

        fixed = 0
        failed = 0

        for asset in assets_without_thumbs:
            model_url = asset.polydata.get("model_url") if asset.polydata else None
            if not model_url:
                if verbosity >= 2:
                    self.stdout.write(f"Skipping {asset.url}: no model_url in polydata")
                failed += 1
                continue

            if verbosity >= 1:
                self.stdout.write(f"Fetching thumbnail data for {model_url}")

            try:
                rows = client.fetch_by_model_url(model_url)
            except Exception as exc:
                self.stdout.write(f"API fetch failed for {model_url}: {exc}")
                failed += 1
                continue

            asset_data = self.normalise_metadata(rows).get(model_url)
            if not asset_data:
                if verbosity >= 2:
                    self.stdout.write(f"No metadata found for {model_url}")
                failed += 1
                continue

            thumbnail_entry = asset_data.preferred_image_entry()
            if not thumbnail_entry:
                if verbosity >= 1:
                    self.stdout.write(f"No thumbnail entry found for {model_url}")
                failed += 1
                continue

            if dry_run:
                self.stdout.write(f"Would download thumbnail for {asset.url} from {thumbnail_entry.uri}")
                fixed += 1
                continue

            if verbosity >= 1:
                self.stdout.write(f"Downloading thumbnail from {thumbnail_entry.uri}")

            file_obj, content_type, size, diagnostics = self.download_thumbnail(thumbnail_entry)
            if file_obj:
                asset.thumbnail.save(file_obj.name, file_obj, save=True)
                asset.thumbnail_contenttype = content_type
                asset.save(update_fields=["thumbnail_contenttype"])
                if verbosity >= 1:
                    self.stdout.write(
                        f"Saved thumbnail for {asset.url}: {file_obj.name} ({size} bytes); {diagnostics}"
                    )
                fixed += 1
            else:
                if verbosity >= 1:
                    self.stdout.write(f"Failed to download thumbnail for {asset.url}; {diagnostics}")
                failed += 1

        self.stdout.write(f"Thumbnail fix complete: {fixed} fixed, {failed} failed")

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
                if not self.should_include_entry(entry):
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

    def apply_open_access_metadata(
        self,
        asset: SmithsonianAsset,
        oa_record: Dict[str, object],
        verbosity: int,
    ) -> None:
        """Apply Open Access metadata to a single asset."""
        # Extract metadata from the Open Access record
        content = oa_record.get("content", {})
        unit_code = oa_record.get("unitCode")

        # Extract descriptiveNonRepeating fields
        desc_non_rep = content.get("descriptiveNonRepeating", {})
        if isinstance(desc_non_rep, dict):
            if not asset.record_id:
                asset.record_id = desc_non_rep.get("record_ID")
            if not asset.record_link:
                asset.record_link = desc_non_rep.get("record_link")
            if not asset.unit_code and desc_non_rep.get("unit_code"):
                asset.unit_code = desc_non_rep.get("unit_code")

            # Extract title/object name
            title_data = desc_non_rep.get("title", {})
            if isinstance(title_data, dict):
                object_name = title_data.get("content") or title_data.get("label")
                if object_name and not asset.object_name:
                    asset.object_name = object_name

        # Use top-level unitCode if not set
        if not asset.unit_code and unit_code:
            asset.unit_code = unit_code

        # Extract freetext fields
        freetext = content.get("freetext", {})
        if isinstance(freetext, dict):
            # Get description from notes
            if not asset.description:
                notes = freetext.get("notes", [])
                if isinstance(notes, list):
                    # Combine summary and brief description
                    descriptions = []
                    for note in notes:
                        if isinstance(note, dict):
                            label = note.get("label", "").lower()
                            note_content = note.get("content", "")
                            if label in ["summary", "brief description"] and note_content:
                                descriptions.append(note_content)
                    if descriptions:
                        asset.description = "\n\n".join(descriptions)

            # Get license/rights
            if not asset.license:
                rights = freetext.get("objectRights", [])
                if isinstance(rights, list) and rights:
                    for right in rights:
                        if isinstance(right, dict):
                            rights_content = right.get("content", "")
                            if rights_content:
                                asset.license = rights_content
                                break

            # Get credit line
            if not asset.credit:
                credit_line = freetext.get("creditLine", [])
                if isinstance(credit_line, list) and credit_line:
                    for credit in credit_line:
                        if isinstance(credit, dict):
                            credit_content = credit.get("content", "")
                            if credit_content:
                                asset.credit = credit_content
                                break

        # Extract tags from indexedStructured
        indexed = content.get("indexedStructured", {})
        if isinstance(indexed, dict):
            tags_set = set()

            # Get topic tags
            topics = indexed.get("topic", [])
            if isinstance(topics, list):
                for topic in topics:
                    if isinstance(topic, str) and topic.strip():
                        tags_set.add(topic.strip())

            # Get usage_flag tags
            usage_flags = indexed.get("usage_flag", [])
            if isinstance(usage_flags, list):
                for flag in usage_flags:
                    if isinstance(flag, str) and flag.strip():
                        tags_set.add(flag.strip())

            # Get object_type tags
            object_types = indexed.get("object_type", [])
            if isinstance(object_types, list):
                for obj_type in object_types:
                    if isinstance(obj_type, str) and obj_type.strip():
                        tags_set.add(obj_type.strip())

            # Store as sorted list
            if tags_set:
                asset.tags = sorted(tags_set)

        if verbosity >= 1:
            self.stdout.write(
                f"  → Open Access: unit_code={asset.unit_code}, "
                f"record_id={asset.record_id}, license={asset.license}, "
                f"has_description={bool(asset.description)}, tags={len(asset.tags)}"
            )

