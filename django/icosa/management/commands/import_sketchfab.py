import os
import time
import mimetypes
import zipfile
import io
from os.path import basename
from datetime import datetime
from typing import Dict, Generator, Iterable, List, Optional

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from icosa.helpers.file import (
    get_content_type,
    validate_file,
    process_main_file,
    UploadedFormat,
)
from django.core.files.uploadedfile import SimpleUploadedFile
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


IMPORT_SOURCE = "sketchfab"


def parse_iso8601(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Sketchfab returns naive ISO8601 strings; use fromisoformat and set TZ to UTC
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt
    except Exception:
        return None


def sketchfab_license_to_internal(slug: Optional[str]) -> Optional[str]:
    """Map Sketchfab license slugs to internal icosa license codes.

    Supported defaults:
      - cc0 -> CREATIVE_COMMONS_0
      - by  -> CREATIVE_COMMONS_BY_4_0

    Other Sketchfab licenses are currently not mapped to icosa choices by default.
    """
    if not slug:
        return None
    slug = slug.lower().strip()
    if slug == "cc0":
        return "CREATIVE_COMMONS_0"
    if slug == "by":
        # Sketchfab uses CC BY 4.0 today for the BY family.
        return "CREATIVE_COMMONS_BY_4_0"
    if slug == "by-sa":
        return "CREATIVE_COMMONS_BY_SA_4_0"
    if slug == "by-nd":
        return "CREATIVE_COMMONS_BY_ND_4_0"
    if slug == "by-nc":
        return "CREATIVE_COMMONS_NC_4_0"
    if slug == "by-nc-sa":
        return "CREATIVE_COMMONS_NC_SA_4_0"
    if slug == "by-nc-nd":
        return "CREATIVE_COMMONS_NC_ND_4_0"
    # Unhandled licenses (by-nc, by-nd, by-sa, etc.) are not mapped
    return None


def pick_thumbnail_url(model: Dict) -> Optional[str]:
    thumbs = (model or {}).get("thumbnails", {}).get("images", [])
    if not thumbs:
        return None
    # Choose the largest width image available
    thumbs_sorted = sorted(thumbs, key=lambda x: x.get("width", 0), reverse=True)
    return thumbs_sorted[0].get("url")


class SketchfabClient:
    BASE = "https://api.sketchfab.com/v3"

    def __init__(self, token: Optional[str] = None, timeout: int = 30):
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})

    def paged(self, url: str, params: Dict) -> Generator[Dict, None, None]:
        next_url = url
        next_params = params.copy()
        while next_url:
            resp = self.session.get(next_url, params=next_params, timeout=self.timeout)
            if resp.status_code != 200:
                raise CommandError(f"Sketchfab request failed: {resp.status_code} {resp.text}")
            data = resp.json()
            for item in data.get("results", []):
                yield item
            next_url = data.get("next")
            next_params = {}
            # Be nice to the API
            time.sleep(0.1)

    def search_models(
        self,
        *,
        licenses: Iterable[str],
        user: Optional[str] = None,
        downloadable: bool = True,
        per_page: int = 24,
        sort_by: str = "-publishedAt",
    ) -> Generator[Dict, None, None]:
        params = {
            "type": "models",
            "licenses": ",".join(licenses),
            "per_page": per_page,
            "downloadable": str(downloadable).lower(),
            "sort_by": sort_by,
        }
        # The search API accepts a 'user' filter by username.
        if user:
            params["user"] = user
        url = f"{self.BASE}/search"
        yield from self.paged(url, params)

    def list_user_models(
        self,
        *,
        user: str,
        licenses: Optional[Iterable[str]] = None,
        downloadable: bool = True,
        per_page: int = 24,
        sort_by: str = "-publishedAt",
    ) -> Generator[Dict, None, None]:
        """List models for a user via the search endpoint.

        Sketchfab's /models endpoint does not accept a user filter reliably; the documented
        approach is the /search API with `type=models` and `user=<username>`.
        """
        params = {
            "type": "models",
            "user": user,
            "per_page": per_page,
            "sort_by": sort_by,
        }
        if licenses:
            params["licenses"] = ",".join(licenses)
        if downloadable is not None:
            params["downloadable"] = str(downloadable).lower()
        url = f"{self.BASE}/search"
        yield from self.paged(url, params)

    def download_info(self, uid: str) -> Optional[Dict]:
        """Return download info for a model, if accessible.

        Response typically contains keys like 'gltf', 'glb', 'usdz', 'source', each with a 'url'.
        Requires a valid token for most models even if downloadable is true.
        """
        resp = self.session.get(f"{self.BASE}/models/{uid}/download", timeout=self.timeout)
        if resp.status_code == 401:
            # Unauthorized; token required
            return None
        if resp.status_code != 200:
            return None
        return resp.json()


class Command(BaseCommand):
    help = (
        "Import assets from Sketchfab using their API. "
        "Allows filtering by user and license. Defaults to CC0, CC-BY, and CC-BY-SA."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            dest="users",
            metavar="USERNAME",
            action="append",
            default=[],
            help="Sketchfab username to filter by (can be provided multiple times)",
        )
        parser.add_argument(
            "--license",
            dest="licenses",
            default="cc0,by,by-sa",
            help=(
                "Comma-separated Sketchfab license slugs to include. "
                "Defaults to 'cc0,by,by-sa' (CC0 Public Domain, CC BY 4.0, CC BY-SA 4.0)."
            ),
        )
        parser.add_argument(
            "--max",
            dest="max_items",
            type=int,
            default=None,
            help="Maximum number of models to import",
        )
        parser.add_argument(
            "--token",
            dest="token",
            default=os.environ.get("SKETCHFAB_TOKEN") or os.environ.get("DJANGO_SKETCHFAB_TOKEN"),
            help="Sketchfab API token (or set SKETCHFAB_TOKEN env)",
        )
        parser.add_argument(
            "--update-existing",
            dest="update_existing",
            action="store_true",
            help="Update models if they already exist",
        )

    def handle(self, *args, **options):
        users: List[str] = options["users"] or []
        # Normalize user-provided license slugs (accept cc-by-sa -> by-sa)
        raw_licenses = options["licenses"] or "cc0,by,by-sa"
        licenses_in = [x.strip().lower() for x in raw_licenses.split(",") if x.strip()]
        licenses = []
        for l in licenses_in:
            if l in ("cc-by", "cc_by", "by-4.0", "by4.0"):
                licenses.append("by")
            elif l in ("cc-by-sa", "cc_by_sa", "by-sa", "bysa", "by-sa-4.0"):
                licenses.append("by-sa")
            else:
                licenses.append(l)
        max_items = options.get("max_items")
        token = options.get("token")
        update_existing = options.get("update_existing", False)

        client = SketchfabClient(token=token)

        count = 0
        seen = 0
        eligible = 0
        targets: Iterable[Dict]

        if users:
            # Iterate per-user, filtering by license locally if needed
            def iter_all():
                for user in users:
                    if options.get("verbosity", 1) >= 2:
                        self.stdout.write(f"Querying user='{user}' licenses={licenses} downloadable=true")
                    for model in client.list_user_models(user=user, licenses=licenses, downloadable=True):
                        yield model

            targets = iter_all()
        else:
            # Global search with license filter
            targets = client.search_models(licenses=licenses)

        for model in targets:
            seen += 1
            # Enforce license filter if the endpoint didn't do it for us
            lic = (model.get("license") or {}).get("label")
            lic_slug = None
            if lic:
                # Derive a slug-like form from label when not present
                l = lic.lower()
                if "cc0" in l or "public domain" in l:
                    lic_slug = "cc0"
                elif "sharealike" in l or "share alike" in l:
                    lic_slug = "by-sa"
                elif "attribution" in l and "no" not in l and "non" not in l:
                    # Heuristic for CC BY
                    lic_slug = "by"
            if users and licenses and lic_slug and lic_slug not in licenses:
                if options.get("verbosity", 1) >= 3:
                    self.stdout.write(f"Skipping by license: {model.get('uid')} label={lic}")
                continue

            uid = model.get("uid")
            if not uid:
                continue

            # If max reached, stop early
            if max_items is not None and count >= max_items:
                break

            # Skip non-downloadable models when we cannot fetch direct file URLs
            if not model.get("isDownloadable", False):
                if options.get("verbosity", 1) >= 2:
                    self.stdout.write(f"Skipping not-downloadable: {model.get('uid')} {model.get('name')}")
                continue

            eligible += 1

            try:
                asset = self.create_or_update_asset_from_model(client, model, update_existing=update_existing)
                if asset is not None:
                    count += 1
                    self.stdout.write(f"Imported {asset.url} ({asset.name})")
            except CommandError as exc:
                self.stderr.write(f"Skipping {uid}: {exc}")

        if options.get("verbosity", 1) >= 1:
            self.stdout.write(f"Seen={seen}, eligible(downloadable+license)={eligible}, imported={count}")
        self.stdout.write(self.style.SUCCESS(f"Finished. Imported {count} models."))

    def create_or_update_asset_from_model(
        self,
        client: SketchfabClient,
        model: Dict,
        *,
        update_existing: bool = False,
    ) -> Optional[Asset]:
        uid = model.get("uid")
        if not uid:
            raise CommandError("Missing uid in model data")

        asset_url = f"sketchfab-{uid}"

        # Lookup existing
        asset = Asset.objects.filter(url=asset_url).first()
        created = False
        if not asset:
            created = True
            asset = Asset(url=asset_url)
        else:
            if not update_existing:
                # Nothing to do
                return None

        # Prepare owner
        user = model.get("user") or {}
        username = (user.get("username") or "").strip() or f"user-{user.get('uid','unknown')}"
        displayname = user.get("displayName") or username
        owner_slug = f"sketchfab-{username}"
        owner, _ = AssetOwner.objects.get_or_create(
            url=owner_slug,
            defaults={
                "displayname": displayname,
                "imported": True,
                "is_claimed": False,
            },
        )

        # Timestamps
        created_at = parse_iso8601(model.get("createdAt")) or timezone.now()
        updated_at = parse_iso8601(model.get("publishedAt")) or created_at

        # Map license
        license_label = (model.get("license") or {}).get("label")
        license_slug = None
        if license_label:
            low = license_label.lower()
            if "cc0" in low or "public domain" in low:
                license_slug = "cc0"
            elif "sharealike" in low or "share alike" in low:
                license_slug = "by-sa"
            elif "attribution" in low and "no" not in low and "non" not in low:
                license_slug = "by"
        internal_license = sketchfab_license_to_internal(license_slug)

        # Core fields
        if created and not asset.create_time:
            asset.create_time = created_at
        asset.update_time = updated_at
        asset.name = model.get("name")
        asset.description = model.get("description")
        asset.visibility = PUBLIC
        asset.state = ASSET_STATE_COMPLETE
        asset.owner = owner
        asset.imported_from = IMPORT_SOURCE
        asset.polydata = model  # Store raw sketchfab metadata
        asset.historical_likes = int(model.get("likeCount") or 0)
        asset.historical_views = int(model.get("viewCount") or 0)
        if internal_license:
            asset.license = internal_license

        # Category mapping (first category name if provided)
        cat_name = None
        cats = model.get("categories") or []
        if cats:
            # categories sometimes carry only name strings
            c0 = cats[0]
            if isinstance(c0, dict):
                cat_name = c0.get("name")
            elif isinstance(c0, str):
                cat_name = c0
        if cat_name:
            key = str(cat_name).strip().lower()
            asset.category = CATEGORY_LABEL_MAP.get(key)

        # Assign an id for new assets
        if created:
            asset.id = generate_snowflake()

        asset.save()

        # Tags
        tags = model.get("tags") or []
        tag_names = []
        for t in tags:
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

        # Thumbnail: download and store locally if possible
        if not asset.thumbnail:
            thumb_url = pick_thumbnail_url(model)
            if thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=20)
                    if resp.status_code == 200:
                        content_type = resp.headers.get("Content-Type")
                        ext = mimetypes.guess_extension(content_type or "") or ".jpg"
                        if ext == ".jpe":
                            ext = ".jpg"
                        filename = f"thumbnail-{uid}{ext}"
                        asset.thumbnail.save(filename, ContentFile(resp.content), save=False)
                        asset.thumbnail_contenttype = content_type or "image/jpeg"
                        asset.save()
                except Exception:
                    # Non-fatal
                    pass

        # Formats/resources: prefer GLB if available, and download into storage
        download = client.download_info(uid)
        if not download:
            raise CommandError(
                "Could not fetch download URLs. Ensure the model is downloadable and a valid token is provided via --token or SKETCHFAB_TOKEN."
            )

        created_any_format = False

        def download_to_contentfile(url: str, *, timeout: int = 60) -> Optional[ContentFile]:
            try:
                resp = requests.get(url, timeout=timeout)
                if resp.status_code != 200:
                    return None
                return ContentFile(resp.content)
            except Exception:
                return None

        def add_format_from_url(url: str, fmt_type: str, *, role: Optional[str] = None, filename: Optional[str] = None):
            nonlocal created_any_format
            data = download_to_contentfile(url)
            if not data:
                return
            # Infer filename and content type
            content_type = None
            try:
                # attempt to fetch content type via HEAD for better accuracy
                head = requests.head(url, timeout=15, allow_redirects=True)
                content_type = head.headers.get("Content-Type")
            except Exception:
                pass
            guessed_ext = mimetypes.guess_extension(content_type or "") or os.path.splitext(url.split("?")[0])[1] or ".bin"
            if guessed_ext == ".jpe":
                guessed_ext = ".jpg"
            name = filename or f"{fmt_type.lower()}-{uid}{guessed_ext}"

            fmt = Format.objects.create(asset=asset, format_type=fmt_type, role=role)
            # Saving file to storage via FileField
            res = Resource(asset=asset, format=fmt, contenttype=content_type or get_content_type(name) or "application/octet-stream")
            res.file.save(name, data, save=True)
            fmt.add_root_resource(res)
            created_any_format = True

        def add_formats_from_zip(url: str, *, preferred_ext_order: Optional[List[str]] = None):
            nonlocal created_any_format
            if preferred_ext_order is None:
                preferred_ext_order = [
                    "glb",
                    "gltf",
                    "fbx",
                    "obj",
                    "usdz",
                    "ply",
                    "stl",
                    "vox",
                    "tilt",
                    "blocks",
                ]
            try:
                resp = requests.get(url, timeout=90)
                if resp.status_code != 200:
                    return
                zf = zipfile.ZipFile(io.BytesIO(resp.content))
            except Exception:
                return

            # Build UploadedFormats from zip members
            uploaded: List[UploadedFormat] = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                fname = info.filename
                # Ignore hidden or MACOSX metadata
                base = basename(fname)
                if not base or base.startswith(".__") or "/." in fname or base.startswith("."):
                    continue
                try:
                    with zf.open(info) as fp:
                        data = fp.read()
                except Exception:
                    continue
                # Construct an in-memory uploaded file
                su = SimpleUploadedFile(base, data, content_type=get_content_type(base) or "application/octet-stream")
                ext = base.split(".")[-1].lower() if "." in base else ""
                details = validate_file(su, ext)
                if details is not None:
                    uploaded.append(details)

            if not uploaded:
                return

            # Choose mainfile by extension preference first, then by mainfile flag
            def pref_index(ext: str) -> int:
                try:
                    return preferred_ext_order.index(ext)
                except ValueError:
                    return len(preferred_ext_order) + 100

            # Filter potential mains
            mains = [u for u in uploaded if u.mainfile]
            if not mains:
                mains = uploaded
            # Choose by extension order on the original filename
            mains_sorted = sorted(mains, key=lambda u: pref_index(u.file.name.split(".")[-1].lower()))
            main = mains_sorted[0]
            subs = [u for u in uploaded if u is not main]

            # Hand off to existing helper to build Format + Resources in storage
            process_main_file(main, subs, asset, gltf_to_convert=None)
            created_any_format = True

        # The download payload usually has entries like {'glb': {'url': ...}, 'gltf': {'url': ...}, 'usdz': {'url': ...}}
        glb_url = (download.get("glb") or {}).get("url")
        if glb_url:
            add_format_from_url(glb_url, "GLB", role="SKETCHFAB_GLB")

        # Provide USDZ if present (not viewer-preferred, but useful to store)
        usdz_url = (download.get("usdz") or {}).get("url")
        if usdz_url:
            add_format_from_url(usdz_url, "USDZ", role="SKETCHFAB_USDZ")

        # GLTF archive (zip): unpack to root + resources
        gltf_url = (download.get("gltf") or {}).get("url")
        if gltf_url:
            add_formats_from_zip(gltf_url, preferred_ext_order=["gltf", "glb", "fbx", "obj"])  # prefer GLTF as main

        # Source archive (zip): prefer FBX, then OBJ, then others
        source_url = (download.get("source") or {}).get("url")
        if source_url:
            add_formats_from_zip(source_url, preferred_ext_order=["fbx", "obj", "gltf", "glb", "ply", "stl"])  # prefer authoring formats

        # Assign preferred viewer format if possible
        asset.assign_preferred_viewer_format()
        # Final save in case any denorms/validations occur
        asset.save()

        return asset
