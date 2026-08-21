from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from icosa.management.commands.seed_assets import Command
from icosa.models import Asset, AssetOwner, Format, Resource, Tag


class SeedAssetsCommandTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)

    @patch("icosa.management.commands.seed_assets.requests.Session.get")
    def test_seeds_assets_and_is_idempotent(self, get):
        api_response = Mock()
        api_response.json.return_value = {"assets": [self.asset_data()]}
        thumbnail_response = Mock(
            content=b"thumbnail",
            headers={"Content-Type": "image/png"},
        )
        get.side_effect = [api_response, thumbnail_response, api_response]

        output = StringIO()
        with override_settings(MEDIA_ROOT=self.media_directory.name):
            call_command("seed_assets", stdout=output)
            call_command("seed_assets", stdout=output)

        api_response.raise_for_status.assert_called()
        thumbnail_response.raise_for_status.assert_called_once()
        self.assertEqual(get.call_args_list[0].kwargs["params"], {"pageSize": 20, "pageToken": 1})
        self.assertEqual(Asset.objects.count(), 1)
        self.assertEqual(AssetOwner.objects.count(), 1)
        self.assertEqual(Tag.objects.count(), 1)
        self.assertEqual(Format.objects.count(), 1)
        self.assertEqual(Resource.objects.count(), 2)

        asset = Asset.objects.get(url="sample-asset")
        self.assertEqual(asset.license, "CREATIVE_COMMONS_BY_3_0")
        self.assertEqual(asset.owner.displayname, "Sample Artist")
        self.assertEqual(asset.raw_tags, "sample")
        self.assertEqual(asset.format_set.get().root_resource.external_url, "https://media.example/model.glb")
        self.assertIn("1 imported, 0 skipped", output.getvalue())
        self.assertIn("0 imported, 1 skipped", output.getvalue())

    @patch("icosa.management.commands.seed_assets.requests.Session.get")
    def test_accepts_null_update_time(self, get):
        asset_data = self.asset_data()
        asset_data["updateTime"] = None
        api_response = Mock()
        api_response.json.return_value = {"assets": [asset_data]}
        thumbnail_response = Mock(
            content=b"thumbnail",
            headers={"Content-Type": "image/png"},
        )
        get.side_effect = [api_response, thumbnail_response]

        with override_settings(MEDIA_ROOT=self.media_directory.name):
            call_command("seed_assets")

        self.assertIsNone(Asset.objects.get(url="sample-asset").update_time)

    def test_maps_api_cc0_to_local_license(self):
        self.assertEqual(
            Command._local_license({"license": "CC0"}),
            "CREATIVE_COMMONS_0",
        )

    @staticmethod
    def asset_data():
        return {
            "assetId": "sample-asset",
            "authorId": "sample-artist",
            "authorName": "Sample Artist",
            "displayName": "Sample Asset",
            "description": "A seeded asset",
            "createTime": "2025-01-01T12:00:00Z",
            "updateTime": "2025-01-02T12:00:00Z",
            "visibility": "PUBLIC",
            "tags": ["sample"],
            "isCurated": True,
            "thumbnail": {
                "relativePath": "thumbnail.png",
                "contentType": "image/png",
                "url": "https://media.example/thumbnail.png",
            },
            "triangleCount": 12,
            "license": "CREATIVE_COMMONS_BY",
            "licenseVersion": "3.0",
            "isIcosaGalleryCompatible": True,
            "presentationParams": {},
            "formats": [
                {
                    "root": {
                        "relativePath": "model.glb",
                        "contentType": "model/gltf-binary",
                        "url": "https://media.example/model.glb",
                    },
                    "resources": [
                        {
                            "relativePath": "texture.png",
                            "contentType": "image/png",
                            "url": "https://media.example/texture.png",
                        }
                    ],
                    "formatComplexity": {"triangleCount": 12},
                    "formatType": "GLB",
                    "role": "GLB_FORMAT",
                    "isPreferredForDownload": True,
                    "isPreferredForGalleryViewer": True,
                    "isCorsAllowed": True,
                }
            ],
        }
