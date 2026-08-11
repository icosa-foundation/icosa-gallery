from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, TestCase, override_settings

from icosa.management.commands.import_polyhaven_local import Command as PolyHavenCommand
from icosa.management.commands.import_sketchfab import (
    sketchfab_license_to_internal,
)


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
