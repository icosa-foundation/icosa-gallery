import json
import io
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from django.utils import timezone
from PIL import Image

from icosa.helpers.file import get_content_type
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
from icosa.models.common import CATEGORY_LABEL_MAP


IMPORT_SOURCE = "Poly Haven"


def first_json_file(path: Path) -> Optional[Path]:
    for p in sorted(path.glob("*.json")):
        return p
    return None


def pick_thumbnail_file(path: Path) -> Optional[Path]:
    """Only use an exact "thumbnail.webp" if present; otherwise no thumbnail."""
    thumb_webp = path / "thumbnail.webp"
    if thumb_webp.exists() and thumb_webp.is_file():
        return thumb_webp
    return None


def pick_glb_file(path: Path) -> Optional[Path]:
    glbs = sorted(path.glob("*.glb"))
    if glbs:
        # If multiple, prefer one that does not look like LOD or low-res
        preferred = [
            p
            for p in glbs
            if not any(k in p.name.lower() for k in ("lod", "low", "preview", "thumb"))
        ]
        return preferred[0] if preferred else glbs[0]
    return None


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Try ISO first
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def derive_license(meta: dict) -> Optional[str]:
    raw = None
    for key in ("license", "licence", "license_id", "licenseName", "license_slug"):
        v = meta.get(key)
        if v:
            raw = str(v)
            break
    if raw:
        low = raw.lower()
        if "cc0" in low or "public domain" in low or "creative commons 0" in low:
            return "CREATIVE_COMMONS_0"
        if "by-sa" in low:
            return "CREATIVE_COMMONS_BY_SA_4_0"
        if low in ("by", "cc-by", "creative commons by", "cc by"):
            return "CREATIVE_COMMONS_BY_4_0"
    return None


class Command(BaseCommand):
    help = (
        "Import local Poly Haven-style assets from a directory. "
        "Each subdirectory is treated as an asset folder; directories without a .glb are ignored."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-dir",
            dest="base_dir",
            default=os.environ.get("POLYHAVEN_DIR") or ".",
            help="Base directory containing Poly Haven asset folders (default: current directory)",
        )
        parser.add_argument(
            "--max",
            dest="max_items",
            type=int,
            default=None,
            help="Maximum number of items to import",
        )
        parser.add_argument(
            "--update-existing",
            dest="update_existing",
            action="store_true",
            help="Update assets if they already exist",
        )
        parser.add_argument(
            "--owner",
            dest="owner_slug",
            default="polyhaven",
            help="Owner slug to assign when author is not derivable",
        )

    def handle(self, *args, **options):
        base_dir = Path(options["base_dir"]).expanduser()
        if not base_dir.exists() or not base_dir.is_dir():
            raise CommandError(f"Base directory does not exist: {base_dir}")

        update_existing: bool = options.get("update_existing", False)
        max_items: Optional[int] = options.get("max_items")
        owner_slug_default: str = options.get("owner_slug")

        count = 0
        scanned = 0
        imported_dirs: List[Path] = []

        for root, _dirs, _files in os.walk(base_dir):
            dirpath = Path(root)
            scanned += 1
            glb = pick_glb_file(dirpath)
            if not glb:
                continue
            try:
                asset = self.create_or_update_from_dir(dirpath, glb, owner_slug_default, update_existing)
                if asset is not None:
                    count += 1
                    imported_dirs.append(dirpath)
                    self.stdout.write(f"Imported {asset.url} from {dirpath.name}")
            except CommandError as exc:
                self.stderr.write(f"Skipping {dirpath.name}: {exc}")

            if max_items is not None and count >= max_items:
                break

        self.stdout.write(self.style.SUCCESS(f"Finished. Scanned={scanned} imported={count}"))

    def create_or_update_from_dir(
        self,
        dirpath: Path,
        glb_path: Path,
        owner_slug_default: str,
        update_existing: bool,
    ) -> Optional[Asset]:
        meta_path = first_json_file(dirpath)
        meta: dict = {}
        meta_present = False
        if meta_path and meta_path.exists():
            meta_present = True
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}

        # Derive basic fields
        name = meta.get("name") or meta.get("title") or dirpath.name
        desc = meta.get("description") or meta.get("desc")

        # Prefer an explicit id/slug; else folder name
        ident = (
            str(meta.get("id") or meta.get("slug") or slugify(name) or dirpath.name)
            .strip()
            .replace(" ", "-")
        )
        asset_url = f"polyhaven-{ident}"

        # Owner: try author info; else default
        author_name = None
        for key in ("author", "artist", "creator"):
            v = meta.get(key)
            if isinstance(v, str) and v.strip():
                author_name = v.strip()
                break
            if isinstance(v, dict):
                author_name = (v.get("name") or v.get("username") or v.get("id") or "").strip() or None
                if author_name:
                    break
        if not author_name and isinstance(meta.get("authors"), list) and meta.get("authors"):
            first = meta["authors"][0]
            if isinstance(first, dict):
                author_name = (first.get("name") or first.get("username") or first.get("id") or "").strip() or None
            elif isinstance(first, str):
                author_name = first.strip()
        owner_slug = slugify(author_name) if author_name else owner_slug_default
        owner_display = author_name or owner_slug_default
        owner, _ = AssetOwner.objects.get_or_create(
            url=owner_slug,
            defaults={
                "displayname": owner_display,
                "imported": True,
                "is_claimed": False,
            },
        )

        # Locate or create asset
        asset = Asset.objects.filter(url=asset_url).first()
        created = False
        if not asset:
            created = True
            asset = Asset(url=asset_url)
        else:
            if not update_existing:
                return None

        # Core fields
        created_at = parse_datetime(meta.get("created") or meta.get("created_at") or meta.get("date")) or timezone.now()
        updated_at = parse_datetime(meta.get("updated") or meta.get("modified") or meta.get("updated_at")) or created_at

        asset.name = name
        asset.description = desc
        if created and not asset.create_time:
            asset.create_time = created_at
        asset.update_time = updated_at
        asset.visibility = PUBLIC
        asset.curated = True
        asset.state = ASSET_STATE_COMPLETE
        asset.owner = owner
        asset.imported_from = IMPORT_SOURCE
        if meta_present:
            asset.polydata = meta
        # All Poly Haven assets are CC0
        asset.license = "CREATIVE_COMMONS_0"

        # Category
        cat_name = None
        cats = meta.get("categories") or meta.get("category")
        if isinstance(cats, list) and cats:
            c0 = cats[0]
            cat_name = c0.get("name") if isinstance(c0, dict) else str(c0)
        elif isinstance(cats, str):
            cat_name = cats
        if cat_name:
            key = str(cat_name).strip().lower()
            asset.category = CATEGORY_LABEL_MAP.get(key)

        # Assign id for new assets
        if created:
            asset.id = generate_snowflake()

        asset.save()

        # Tags
        tags_raw: Iterable = meta.get("tags") or meta.get("keywords") or []
        tag_names: List[str] = []
        for t in tags_raw:
            if isinstance(t, dict):
                tag_names.append(t.get("name") or t.get("slug"))
            elif isinstance(t, str):
                tag_names.append(t)
        tag_objs = []
        for name in filter(None, set(tag_names)):
            tag, _ = Tag.objects.get_or_create(name=name)
            tag_objs.append(tag)
        if tag_objs:
            asset.tags.set(tag_objs)

        # Thumbnail
        thumb_path = pick_thumbnail_file(dirpath)
        if thumb_path and ((not asset.thumbnail) or update_existing):
            # Convert webp to jpeg to satisfy thumbnail validators
            if thumb_path.suffix.lower() == ".webp":
                with Image.open(thumb_path) as im:
                    # Ensure RGB (discard alpha on white background if present)
                    if im.mode in ("RGBA", "LA"):
                        bg = Image.new("RGB", im.size, (255, 255, 255))
                        alpha = im.split()[-1] if im.mode in ("RGBA", "LA") else None
                        if alpha is not None:
                            bg.paste(im.convert("RGB"), mask=alpha)
                        else:
                            bg.paste(im.convert("RGB"))
                        im = bg
                    else:
                        im = im.convert("RGB")
                    # Fit image into an 8:5 box without upscaling image content.
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
                    # Add 10% white padding around the image
                    pad = int(0.1 * max(canvas_w, canvas_h))
                    padded_w = canvas_w + 2 * pad
                    padded_h = canvas_h + 2 * pad
                    canvas = Image.new("RGB", (padded_w, padded_h), (255, 255, 255))
                    # Center the image on the padded canvas
                    paste_x = (padded_w - canvas_w) // 2
                    paste_y = (padded_h - canvas_h) // 2
                    inner_canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
                    img_x = (canvas_w - new_w) // 2
                    img_y = (canvas_h - new_h) // 2
                    inner_canvas.paste(im, (img_x, img_y))
                    canvas.paste(inner_canvas, (paste_x, paste_y))
                    buf = io.BytesIO()
                    canvas.save(buf, format="JPEG", quality=90)
                    buf.seek(0)
                    jpg_name = thumb_path.with_suffix(".jpg").name
                    asset.thumbnail.save(jpg_name, ContentFile(buf.read()), save=False)
                    asset.thumbnail_contenttype = "image/jpeg"

            else:
                # Guess content type and save
                content_type = get_content_type(thumb_path.name) or mimetypes.guess_type(thumb_path.name)[0] or "image/jpeg"
                asset.thumbnail.save(thumb_path.name, ContentFile(thumb_path.read_bytes()), save=False)
                asset.thumbnail_contenttype = content_type
            asset.save()

        # Formats/resources: attach GLB as primary format (avoid duplicates)
        existing_glb = asset.format_set.filter(format_type="GLB").last()
        if not existing_glb:
            fmt = Format.objects.create(asset=asset, format_type="GLB", role="POLYHAVEN_GLB")
            glb_bytes = glb_path.read_bytes()
            content_type = get_content_type(glb_path.name) or mimetypes.guess_type(glb_path.name)[0] or "application/octet-stream"
            res = Resource(asset=asset, format=fmt, contenttype=content_type)
            res.file.save(glb_path.name, ContentFile(glb_bytes), save=True)
            fmt.add_root_resource(res)

        # Assign preferred viewer format and save
        asset.assign_preferred_viewer_format()
        asset.save()

        return asset
