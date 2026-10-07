from contextlib import nullcontext
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.parse import urljoin

from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase

from icosa.models import Format, Resource


class ExternalLocalizationTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.storage = FileSystemStorage(location=directory.name)
        self.enterContext(patch.object(Resource._meta.get_field("file"), "storage", self.storage))
        self.enterContext(patch("icosa.models.format.get_cloud_media_root", return_value=""))
        self.enterContext(patch("icosa.models.format.get_cached_cors_allow_list", return_value=[]))
        self.enterContext(patch("icosa.models.format.cache.delete_many"))
        self.enterContext(patch("icosa.models.format.transaction.atomic", side_effect=nullcontext))
        self.enterContext(
            patch("icosa.models.format.download_to_tempfile", side_effect=lambda *args, **kwargs: BytesIO(b"content"))
        )

    def make_format(self, root_url, *resource_urls):
        resources = [Resource(pk=i, external_url=url) for i, url in enumerate([root_url, *resource_urls], start=1)]
        for resource in resources:
            resource.save = Mock()
        format = Mock(pk=1, format_type="GLTF2", root_resource=resources[0], zip_archive_url=None)
        format.asset.owner.id = 2
        format.asset.id = 3
        format.resource_set.all.return_value = resources[1:]
        format.get_all_resources.return_value = resources
        return format, resources

    def test_parent_relative_resources_preserve_layout(self):
        format, (root, texture) = self.make_format(
            "https://example.com/asset/models/model.gltf", "https://example.com/asset/textures/albedo.png"
        )

        Format.localize_external_resources(format)

        self.assertEqual(root.uploaded_file_path, "models/model.gltf")
        self.assertEqual(texture.uploaded_file_path, "textures/albedo.png")
        self.assertEqual(urljoin(root.file.name, "../textures/albedo.png"), texture.file.name)
        self.assertTrue(self.storage.exists(texture.file.name))
        self.assertIsNone(texture.external_url)

    def test_descendant_paths_keep_original_names(self):
        format, (root, texture) = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/textures/base%20color.png?download=1"
        )

        Format.localize_external_resources(format)

        self.assertEqual(root.uploaded_file_path, "model.gltf")
        self.assertEqual(texture.uploaded_file_path, "textures/base color.png")
        self.assertEqual(urljoin(root.file.name, "textures/base color.png"), texture.file.name)

    def test_local_resources_clear_external_archive(self):
        format, (root,) = self.make_format("https://example.com/asset/model.gltf")
        root.file.name = "poly/model.gltf"
        format.zip_archive_url = "https://example.com/asset/archive.zip"

        self.assertEqual(Format.localize_external_resources(format), [])

        self.assertIsNone(format.zip_archive_url)
        format.save.assert_called_once_with()
