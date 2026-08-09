import mimetypes
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from icosa.helpers.file import get_content_type
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import (
    ASSET_STATE_COMPLETE,
    ASSET_VISIBILITY_CHOICES,
    LICENSE_CHOICES,
    PRIVATE,
    Asset,
    AssetCollection,
    AssetCollectionAsset,
    AssetOwner,
    Format,
    Resource,
)


MODEL_FORMATS = {
    ".fbx": ("FBX", "ORIGINAL_FBX_FORMAT"),
    ".glb": ("GLB", "GLB_FORMAT"),
    ".obj": ("OBJ", "ORIGINAL_TRIANGULATED_OBJ_FORMAT"),
}
PREVIEW_EXTENSIONS = (".png", ".jpg", ".jpeg")
VERSION_SUFFIX = re.compile(r"(?:[\s_-]+v?\d+(?:\.\d+)*)$")


class OverviewTitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split())


def is_pack_directory(path: Path) -> bool:
    return (path / "Models").is_dir() and (path / "Previews").is_dir()


def discover_pack_directories(root: Path) -> list[Path]:
    if is_pack_directory(root):
        return [root]
    directories = sorted(path for path in root.iterdir() if path.is_dir())
    invalid_directories = [path for path in directories if not is_pack_directory(path)]
    if invalid_directories:
        invalid_names = ", ".join(path.name for path in invalid_directories)
        raise CommandError(
            "Every immediate subdirectory must contain Models and Previews "
            f"directories; invalid: {invalid_names}"
        )
    return directories


def read_collection_name(pack_path: Path, batch_root: Path) -> str:
    overview_path = pack_path / "Overview.html"
    if overview_path.is_file():
        parser = OverviewTitleParser()
        parser.feed(overview_path.read_text(encoding="utf-8", errors="replace"))
        if parser.title:
            return parser.title

    name = pack_path.name
    parent_prefix = f"{batch_root.name}_"
    if name.casefold().startswith(parent_prefix.casefold()):
        name = name[len(parent_prefix) :]
    name = VERSION_SUFFIX.sub("", name)
    return re.sub(r"[_-]+", " ", name).strip().title()


def discover_models(pack_path: Path) -> dict[str, dict[str, Path]]:
    models: dict[str, dict[str, Path]] = {}
    for path in sorted((pack_path / "Models").rglob("*")):
        extension = path.suffix.lower()
        if not path.is_file() or extension not in MODEL_FORMATS:
            continue
        formats = models.setdefault(path.stem, {})
        if extension in formats:
            raise CommandError(
                f"Multiple {extension} files found for {path.stem} in {pack_path}"
            )
        formats[extension] = path
    return models


def find_preview(pack_path: Path, stem: str) -> Optional[Path]:
    preview_dir = pack_path / "Previews"
    for extension in PREVIEW_EXTENSIONS:
        candidate = preview_dir / f"{stem}{extension}"
        if candidate.is_file():
            return candidate
    return None


def detect_license(pack_path: Path) -> Optional[str]:
    license_path = pack_path / "License.txt"
    if not license_path.is_file():
        return None
    text = license_path.read_text(encoding="utf-8", errors="replace").casefold()
    if "creative commons zero" in text or re.search(r"\bcc0\b", text):
        return "CREATIVE_COMMONS_0"
    return None


def dependent_files(model_path: Path) -> Iterable[tuple[Path, str]]:
    if model_path.suffix.lower() == ".obj":
        material = model_path.with_suffix(".mtl")
        if material.is_file():
            yield material, material.name

    if model_path.suffix.lower() == ".fbx":
        sidecar_dir = model_path.with_suffix(".fbm")
        if sidecar_dir.is_dir():
            for path in sorted(sidecar_dir.rglob("*")):
                if path.is_file():
                    yield path, path.relative_to(model_path.parent).as_posix()

    texture_dir = model_path.parent / "Textures"
    if texture_dir.is_dir() and model_path.suffix.lower() in {
        ".glb",
        ".obj",
        ".fbx",
    }:
        for path in sorted(texture_dir.rglob("*")):
            if path.is_file():
                yield path, path.relative_to(model_path.parent).as_posix()


def content_type(path: Path) -> str:
    return (
        get_content_type(path.name)
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )


class Command(BaseCommand):
    help = (
        "Import a directory of model packs as static collections. Each immediate "
        "subdirectory containing Models and Previews directories becomes a collection."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "root",
            help="Directory containing one subdirectory per collection",
        )
        parser.add_argument(
            "--owner",
            required=True,
            help="URL of the existing asset owner for the collections and assets",
        )
        parser.add_argument(
            "--visibility",
            choices=[value for value, _label in ASSET_VISIBILITY_CHOICES],
            default=PRIVATE,
            help="Visibility assigned to imported collections and assets",
        )
        parser.add_argument(
            "--license",
            choices=[value for value, _label in LICENSE_CHOICES if value],
            help="Override the license detected from each pack's License.txt",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Replace formats, thumbnails, and metadata for existing imported assets",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report the packs without writing to the database",
        )

    def handle(self, *args, **options):
        root = Path(options["root"]).expanduser().resolve()
        if not root.is_dir():
            raise CommandError(f"Directory does not exist: {root}")

        packs = discover_pack_directories(root)
        if not packs:
            raise CommandError(
                f"No pack directories containing Models and Previews found in {root}"
            )

        owner = AssetOwner.objects.filter(url=options["owner"]).first()
        if owner is None:
            raise CommandError(f"Asset owner does not exist: {options['owner']}")

        plans = []
        seen_collection_urls = set()
        for pack_path in packs:
            name = read_collection_name(pack_path, root)
            collection_url = slugify(name)
            if not collection_url:
                raise CommandError(f"Could not derive a collection URL for {pack_path}")
            if collection_url in seen_collection_urls:
                raise CommandError(
                    f"Multiple packs resolve to the collection URL {collection_url}"
                )
            seen_collection_urls.add(collection_url)

            models = discover_models(pack_path)
            if not models:
                raise CommandError(f"No supported model files found in {pack_path}")
            plans.append((pack_path, name, collection_url, models))
            format_names = sorted(
                {
                    extension[1:]
                    for formats in models.values()
                    for extension in formats
                }
            )
            self.stdout.write(
                f"{name}: {len(models)} assets ({', '.join(format_names)})"
            )

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Validated {len(plans)} collection(s); no changes made"
                )
            )
            return

        total_assets = 0
        for pack_path, name, collection_url, models in plans:
            with transaction.atomic():
                collection, created = AssetCollection.objects.get_or_create(
                    url=collection_url,
                    defaults={
                        "owner": owner,
                        "name": name,
                        "visibility": options["visibility"],
                    },
                )
                if not created:
                    if collection.owner_id != owner.id:
                        raise CommandError(
                            f"Collection URL {collection_url} belongs to another owner"
                        )
                    if collection.is_dynamic:
                        raise CommandError(
                            f"Collection {collection_url} is dynamic and cannot receive explicit assets"
                        )
                    if options["update_existing"]:
                        collection.name = name
                        collection.visibility = options["visibility"]
                        collection.save()

                collection_preview = pack_path / "Preview.png"
                if collection_preview.is_file() and (
                    not collection.image or options["update_existing"]
                ):
                    collection.image.save(
                        collection_preview.name,
                        ContentFile(collection_preview.read_bytes()),
                        save=True,
                    )

                pack_license = options["license"] or detect_license(pack_path)
                for order, (stem, formats) in enumerate(sorted(models.items())):
                    asset_url = f"{collection_url}-{slugify(stem)}"
                    import_marker = f"model-pack:{collection_url}"
                    asset = Asset.objects.filter(url=asset_url).first()
                    if asset is not None and asset.owner_id != owner.id:
                        raise CommandError(
                            f"Asset URL {asset_url} belongs to another owner"
                        )
                    if asset is not None and asset.imported_from != import_marker:
                        raise CommandError(
                            f"Asset URL {asset_url} was not created by this importer"
                        )

                    should_import = asset is None or options["update_existing"]
                    replace = asset is not None
                    if asset is None:
                        asset = Asset(
                            id=generate_snowflake(),
                            url=asset_url,
                            owner=owner,
                        )
                    if should_import:
                        self.import_asset(
                            asset=asset,
                            pack_path=pack_path,
                            collection_url=collection_url,
                            stem=stem,
                            formats=formats,
                            visibility=options["visibility"],
                            license_name=pack_license,
                            replace=replace,
                        )

                    AssetCollectionAsset.objects.update_or_create(
                        collection=collection,
                        asset=asset,
                        defaults={"order": order},
                    )
                    total_assets += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {total_assets} assets into {len(plans)} collection(s)"
            )
        )

    def import_asset(
        self,
        *,
        asset: Asset,
        pack_path: Path,
        collection_url: str,
        stem: str,
        formats: dict[str, Path],
        visibility: str,
        license_name: Optional[str],
        replace: bool,
    ) -> None:
        asset.name = re.sub(r"[_-]+", " ", stem).strip().title()
        asset.visibility = visibility
        asset.license = license_name
        asset.state = ASSET_STATE_COMPLETE
        asset.imported_from = f"model-pack:{collection_url}"
        asset.save()

        if replace:
            asset.resource_set.all().delete()
            asset.format_set.all().delete()

        preview = find_preview(pack_path, stem)
        if preview is not None:
            asset.thumbnail.save(
                preview.name,
                ContentFile(preview.read_bytes()),
                save=False,
            )
            asset.thumbnail_contenttype = content_type(preview)

        for extension, model_path in sorted(formats.items()):
            format_type, role = MODEL_FORMATS[extension]
            format_object = Format.objects.create(
                asset=asset,
                format_type=format_type,
                role=role,
                is_preferred_for_gallery_viewer=extension == ".glb",
                is_preferred_for_download=True,
            )
            root_resource = Resource(
                asset=asset,
                format=format_object,
                contenttype=content_type(model_path),
            )
            root_resource.file.save(
                model_path.name,
                ContentFile(model_path.read_bytes()),
                save=True,
            )
            format_object.add_root_resource(root_resource)

            for dependency, relative_path in dependent_files(model_path):
                resource = Resource(
                    asset=asset,
                    format=format_object,
                    uploaded_file_path=relative_path,
                    contenttype=content_type(dependency),
                )
                resource.file.save(
                    dependency.name,
                    ContentFile(dependency.read_bytes()),
                    save=True,
                )

        asset.save()
