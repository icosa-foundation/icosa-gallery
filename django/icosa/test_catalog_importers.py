from django.test import SimpleTestCase

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
