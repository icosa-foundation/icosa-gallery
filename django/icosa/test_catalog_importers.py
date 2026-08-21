from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from icosa.management.commands.import_polyhaven_local import Command as PolyHavenCommand
from icosa.management.commands.import_sketchfab import Command as SketchfabCommand
from icosa.management.commands.import_smithsonian_models import (
    Command as SmithsonianCommand,
    SmithsonianAsset,
    SmithsonianResource,
)
from icosa.management.commands.import_sketchfab import (
    get_sketchfab_license_slug,
    sketchfab_license_to_internal,
)
from icosa.models import AssetOwner, Format


class SketchfabImporterTests(SimpleTestCase):
    def test_supported_licenses_map_to_asset_license_values(self):
        expected_licenses = {
            "cc0": "CREATIVE_COMMONS_0",
            "by": "CREATIVE_COMMONS_BY_4_0",
            "by-sa": "CREATIVE_COMMONS_BY_SA_4_0",
            "by-nd": "CREATIVE_COMMONS_BY_ND_4_0",
            "by-nc": "CREATIVE_COMMONS_NC_4_0",
            "by-nc-sa": "CREATIVE_COMMONS_NC_SA_4_0",
            "by-nc-nd": "CREATIVE_COMMONS_NC_ND_4_0",
        }

        for sketchfab_license, asset_license in expected_licenses.items():
            with self.subTest(sketchfab_license=sketchfab_license):
                self.assertEqual(
                    sketchfab_license_to_internal(sketchfab_license),
                    asset_license,
                )

    def test_license_labels_preserve_all_restrictions(self):
        expected_slugs = {
            "CC0 Public Domain": "cc0",
            "Creative Commons Attribution": "by",
            "Creative Commons Attribution-ShareAlike": "by-sa",
            "Creative Commons Attribution-NoDerivs": "by-nd",
            "Creative Commons Attribution-NonCommercial": "by-nc",
            "Creative Commons Attribution-NonCommercial-ShareAlike": "by-nc-sa",
            "Creative Commons Attribution-NonCommercial-NoDerivs": "by-nc-nd",
        }

        for label, expected_slug in expected_slugs.items():
            with self.subTest(label=label):
                model = {"license": {"label": label}}
                self.assertEqual(get_sketchfab_license_slug(model), expected_slug)

    def test_license_slug_takes_priority_over_ambiguous_label(self):
        model = {
            "license": {
                "slug": "by-nc-sa",
                "label": "Creative Commons Attribution-ShareAlike",
            }
        }

        self.assertEqual(get_sketchfab_license_slug(model), "by-nc-sa")


class SketchfabUpdateImporterTests(TestCase):
    def test_update_replaces_existing_formats_and_files(self):
        class FakeClient:
            def download_info(self, uid):
                return {"glb": {"url": "https://example.com/model.glb"}}

        class FakeResponse:
            status_code = 200
            headers = {"Content-Type": "model/gltf-binary"}

            def __init__(self, content):
                self.content = content

            def iter_content(self, chunk_size):
                yield self.content

        model = {
            "uid": "model-id",
            "name": "Example",
            "user": {"username": "artist"},
            "license": {"slug": "by"},
        }
        response_content = [b"old glb"]

        with TemporaryDirectory() as directory, override_settings(
            MEDIA_ROOT=directory
        ), patch(
            "icosa.management.commands.import_sketchfab.requests.get",
            side_effect=lambda *args, **kwargs: FakeResponse(response_content[0]),
        ), patch(
            "icosa.management.commands.import_sketchfab.requests.head",
            return_value=FakeResponse(b""),
        ):
            command = SketchfabCommand()
            asset = command.create_or_update_asset_from_model(
                FakeClient(), model, update_existing=False
            )
            old_format = Format.objects.get(asset=asset)
            old_resource = old_format.root_resource
            old_storage_name = old_resource.file.name

            response_content[0] = b"new glb"
            with self.captureOnCommitCallbacks(execute=True):
                asset = command.create_or_update_asset_from_model(
                    FakeClient(), model, update_existing=True
                )

            new_format = Format.objects.get(asset=asset)
            self.assertNotEqual(new_format.pk, old_format.pk)
            with new_format.root_resource.file.open("rb") as imported_glb:
                self.assertEqual(imported_glb.read(), b"new glb")
            self.assertFalse(old_resource.file.storage.exists(old_storage_name))


class PolyHavenImporterTests(TestCase):
    def test_import_marks_glb_as_preferred_and_viewer_compatible(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            asset_directory = Path(directory) / "example"
            asset_directory.mkdir()
            glb_path = asset_directory / "example.glb"
            glb_path.write_bytes(b"glb")

            asset = PolyHavenCommand().create_or_update_from_dir(
                asset_directory,
                glb_path,
                "polyhaven",
                update_existing=False,
            )

            asset.refresh_from_db()
            self.assertEqual(asset.preferred_viewer_format.format_type, "GLB")
            self.assertTrue(asset.is_viewer_compatible)

    def test_update_replaces_imported_glb(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            asset_directory = Path(directory) / "example"
            asset_directory.mkdir()
            glb_path = asset_directory / "example.glb"
            glb_path.write_bytes(b"old glb")
            thumbnail_path = asset_directory / "thumbnail.webp"
            Image.new("RGB", (8, 5), "white").save(thumbnail_path, "WEBP")
            command = PolyHavenCommand()
            asset = command.create_or_update_from_dir(
                asset_directory,
                glb_path,
                "polyhaven",
                update_existing=False,
            )
            old_format = asset.format_set.get(role="POLYHAVEN_GLB")
            old_resource = old_format.root_resource
            old_storage_name = old_resource.file.name
            old_thumbnail_name = asset.thumbnail.name

            glb_path.write_bytes(b"new glb")
            asset = command.create_or_update_from_dir(
                asset_directory,
                glb_path,
                "polyhaven",
                update_existing=True,
            )

            new_format = asset.format_set.get(role="POLYHAVEN_GLB")
            self.assertNotEqual(new_format.pk, old_format.pk)
            with new_format.root_resource.file.open("rb") as imported_glb:
                self.assertEqual(imported_glb.read(), b"new glb")
            self.assertFalse(old_resource.file.storage.exists(old_storage_name))
            self.assertNotEqual(asset.thumbnail.name, old_thumbnail_name)
            self.assertFalse(asset.thumbnail.storage.exists(old_thumbnail_name))


class SmithsonianImporterTests(SimpleTestCase):
    def test_assets_are_processed_after_all_pages_are_aggregated(self):
        model_url = "https://3d.si.edu/object/example"
        first_page_asset = SmithsonianAsset(title="Example", model_url=model_url)
        first_page_asset.add_entry(
            SmithsonianResource(
                uri="https://example.com/model.glb",
                usage="web3d",
                quality="high",
                model_type=None,
                file_type="glb",
            )
        )
        second_page_asset = SmithsonianAsset(title="Example", model_url=model_url)
        second_page_asset.add_entry(
            SmithsonianResource(
                uri="https://example.com/thumbnail.jpg",
                usage="image_thumb",
                quality="low",
                model_type=None,
                file_type="jpg",
            )
        )

        class FakeClient:
            def fetch(self):
                yield "first page"
                yield "second page"

            def fetch_open_access_metadata(self, model_url):
                return None

        imported_entry_counts = []
        command = SmithsonianCommand()
        with patch(
            "icosa.management.commands.import_smithsonian_models.SmithsonianAPIClient",
            return_value=FakeClient(),
        ), patch.object(
            command,
            "ensure_owner",
            return_value=object(),
        ), patch.object(
            command,
            "normalise_metadata",
            side_effect=[
                {model_url: first_page_asset},
                {model_url: second_page_asset},
            ],
        ), patch.object(
            command,
            "populate_missing_image_entries",
        ), patch.object(
            command,
            "find_existing_asset",
            return_value=None,
        ), patch.object(
            command,
            "create_or_update_asset",
            side_effect=lambda asset_data, *args, **kwargs: imported_entry_counts.append(
                (len(asset_data.model_entries), len(asset_data.image_entries))
            )
            or object(),
        ):
            command.handle(
                rows=100,
                rate_limit=0,
                max_assets=None,
                dry_run=False,
                fix_thumbs=False,
                update_existing=False,
                api_key="test",
                verbosity=0,
            )

        self.assertEqual(imported_entry_counts, [(1, 1)])


class SmithsonianUpdateImporterTests(TestCase):
    def test_update_deletes_replaced_thumbnail(self):
        owner = AssetOwner.objects.create(
            url="smithsonian",
            displayname="Smithsonian",
            imported=True,
        )
        asset_data = SmithsonianAsset(
            title="Example",
            model_url="https://3d.si.edu/object/example",
        )
        asset_data.add_entry(
            SmithsonianResource(
                uri="https://example.com/model.glb",
                usage="web3d",
                quality="high",
                model_type=None,
                file_type="glb",
            )
        )
        asset_data.add_entry(
            SmithsonianResource(
                uri="https://example.com/thumbnail.jpg",
                usage="image_thumb",
                quality="low",
                model_type=None,
                file_type="jpg",
            )
        )
        downloaded_thumbnails = [
            (
                ContentFile(b"old thumbnail", name="thumbnail.jpg"),
                "image/jpeg",
                13,
                "",
            ),
            (
                ContentFile(b"new thumbnail", name="thumbnail.jpg"),
                "image/jpeg",
                13,
                "",
            ),
        ]

        with TemporaryDirectory() as directory, override_settings(
            MEDIA_ROOT=directory
        ), patch.object(
            SmithsonianCommand,
            "download_thumbnail",
            side_effect=downloaded_thumbnails,
        ):
            command = SmithsonianCommand()
            asset = command.create_or_update_asset(
                asset_data,
                owner,
                verbosity=0,
                update_existing=False,
            )
            old_thumbnail_name = asset.thumbnail.name

            asset = command.create_or_update_asset(
                asset_data,
                owner,
                verbosity=0,
                update_existing=True,
            )

            self.assertNotEqual(asset.thumbnail.name, old_thumbnail_name)
            self.assertFalse(asset.thumbnail.storage.exists(old_thumbnail_name))
            self.assertTrue(asset.thumbnail.storage.exists(asset.thumbnail.name))
