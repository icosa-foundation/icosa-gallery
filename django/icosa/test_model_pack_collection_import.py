from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings

from icosa.management.commands.import_model_pack_collections import (
    discover_pack_directories,
    read_collection_name,
)
from icosa.models import (
    ASSET_STATE_COMPLETE,
    PRIVATE,
    Asset,
    AssetCollection,
    AssetOwner,
)


class ModelPackCollectionImportTests(TestCase):
    def setUp(self):
        self.owner = AssetOwner.objects.create(
            url="gallery-imports",
            displayname="Gallery Imports",
            imported=True,
            is_claimed=False,
        )

    def make_pack(self, root: Path, directory_name: str, title: str) -> Path:
        pack = root / directory_name
        (pack / "Models" / "GLB format").mkdir(parents=True)
        (pack / "Models" / "FBX format" / "Textures").mkdir(parents=True)
        (pack / "Models" / "OBJ format" / "Textures").mkdir(parents=True)
        (pack / "Previews").mkdir()
        (pack / "Overview.html").write_text(
            f"<html><head><title>{title}</title></head></html>",
            encoding="utf-8",
        )
        (pack / "License.txt").write_text(
            "License: Creative Commons Zero (CC0)",
            encoding="utf-8",
        )
        (pack / "Preview.png").write_bytes(b"collection preview")
        (pack / "Previews" / "stone-wall.png").write_bytes(b"asset preview")
        (pack / "Models" / "GLB format" / "stone-wall.glb").write_bytes(b"glb")
        (pack / "Models" / "FBX format" / "stone-wall.fbx").write_bytes(b"fbx")
        (
            pack / "Models" / "FBX format" / "Textures" / "colors.png"
        ).write_bytes(b"texture")
        (pack / "Models" / "OBJ format" / "stone-wall.obj").write_bytes(b"obj")
        (pack / "Models" / "OBJ format" / "stone-wall.mtl").write_bytes(b"mtl")
        (
            pack / "Models" / "OBJ format" / "Textures" / "colors.png"
        ).write_bytes(b"texture")
        return pack

    def test_batch_root_discovers_each_pack_and_uses_overview_titles(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "Publisher"
            root.mkdir()
            first = self.make_pack(root, "publisher_first-pack_1.0", "First Pack")
            second = self.make_pack(root, "publisher_second-pack", "Second Pack")
            (root / "download.zip").write_bytes(b"ignored")

            self.assertEqual(discover_pack_directories(root), [first, second])
            self.assertEqual(read_collection_name(first, root), "First Pack")

    def test_import_creates_static_collection_with_all_model_formats(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            root = Path(directory) / "Publisher"
            root.mkdir()
            self.make_pack(root, "publisher_castle-pack_2.0", "Castle Pack")

            call_command(
                "import_model_pack_collections",
                str(root),
                owner=self.owner.url,
            )

            collection = AssetCollection.objects.get(url="castle-pack")
            asset = Asset.objects.get(url="castle-pack-stone-wall")
            self.assertEqual(collection.owner, self.owner)
            self.assertEqual(collection.name, "Castle Pack")
            self.assertEqual(collection.visibility, PRIVATE)
            self.assertFalse(collection.is_dynamic)
            self.assertTrue(collection.image)
            self.assertEqual(list(collection.assets.all()), [asset])
            self.assertEqual(asset.name, "Stone Wall")
            self.assertEqual(asset.state, ASSET_STATE_COMPLETE)
            self.assertEqual(asset.license, "CREATIVE_COMMONS_0")
            self.assertEqual(asset.imported_from, "model-pack:castle-pack")
            self.assertTrue(asset.thumbnail)
            self.assertEqual(
                set(asset.format_set.values_list("format_type", flat=True)),
                {"GLB", "FBX", "OBJ"},
            )
            self.assertEqual(
                asset.format_set.get(is_preferred_for_gallery_viewer=True).format_type,
                "GLB",
            )
            obj_format = asset.format_set.get(format_type="OBJ")
            self.assertEqual(obj_format.resource_set.count(), 2)
            self.assertEqual(
                set(obj_format.resource_set.values_list("uploaded_file_path", flat=True)),
                {"stone-wall.mtl", "Textures/colors.png"},
            )
            asset.refresh_from_db()
            self.assertTrue(asset.has_fbx)
            self.assertTrue(asset.has_obj)
            self.assertTrue(asset.is_viewer_compatible)

    def test_repeated_import_does_not_duplicate_assets_or_formats(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            root = Path(directory) / "Publisher"
            root.mkdir()
            self.make_pack(root, "publisher_castle-pack", "Castle Pack")

            for _attempt in range(2):
                call_command(
                    "import_model_pack_collections",
                    str(root),
                    owner=self.owner.url,
                )

            self.assertEqual(Asset.objects.count(), 1)
            self.assertEqual(
                AssetCollection.objects.filter(url="castle-pack").count(),
                1,
            )
            self.assertEqual(Asset.objects.get().format_set.count(), 3)

            call_command(
                "import_model_pack_collections",
                str(root),
                owner=self.owner.url,
                update_existing=True,
            )

            asset = Asset.objects.get()
            self.assertEqual(asset.format_set.count(), 3)
            self.assertEqual(asset.resource_set.count(), 6)

    def test_dry_run_validates_without_writing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "Publisher"
            root.mkdir()
            self.make_pack(root, "publisher_castle-pack", "Castle Pack")

            call_command(
                "import_model_pack_collections",
                str(root),
                owner=self.owner.url,
                dry_run=True,
            )

            self.assertFalse(Asset.objects.exists())
            self.assertFalse(
                AssetCollection.objects.filter(url="castle-pack").exists()
            )
