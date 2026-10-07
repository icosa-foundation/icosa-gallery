from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.parse import urljoin

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase

from icosa.models import Asset, Format, Resource
from icosa.models.format import ExternalResourceLocalizeException


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

    def assert_storage_empty(self):
        self.assertEqual([path for path in Path(self.storage.location).rglob("*") if path.is_file()], [])

    def test_failed_upload_removes_files_and_allows_retry(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png"
        )
        save = self.storage.save
        attempts = 0

        def fail_second_upload(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise OSError("Upload failed")
            return save(*args, **kwargs)

        with patch.object(self.storage, "save", side_effect=fail_second_upload):
            with self.assertRaisesRegex(OSError, "Upload failed"):
                Format.localize_external_resources(format)

        self.assert_storage_empty()
        self.assertTrue(all(not resource.file and resource.external_url for resource in resources))
        self.assertEqual(len(Format.localize_external_resources(format)), 2)

    def test_failed_database_save_removes_files_and_allows_retry(self):
        for fail_archive_save in (False, True):
            with self.subTest(fail_archive_save=fail_archive_save):
                format, resources = self.make_format("https://example.com/asset/model.gltf")
                archive_url = "https://example.com/asset/archive.zip"
                format.zip_archive_url = archive_url
                save = format.save if fail_archive_save else resources[0].save
                save.side_effect = RuntimeError("Database save failed")

                with self.assertRaisesRegex(RuntimeError, "Database save failed"):
                    Format.localize_external_resources(format)

                self.assert_storage_empty()
                self.assertFalse(resources[0].file)
                self.assertIsNotNone(resources[0].external_url)
                self.assertEqual(format.zip_archive_url, archive_url)
                save.side_effect = None
                self.assertEqual(len(Format.localize_external_resources(format)), 1)
                self.storage.delete(resources[0].file.name)

    def test_collision_removes_new_files_and_preserves_existing_file(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png"
        )
        existing_name = self.storage.save("2/3/GLTF2/model.gltf", ContentFile(b"existing"))

        with self.assertRaises(ExternalResourceLocalizeException):
            Format.localize_external_resources(format)

        stored_files = [path for path in Path(self.storage.location).rglob("*") if path.is_file()]
        self.assertEqual(stored_files, [Path(self.storage.path(existing_name))])
        self.assertEqual(stored_files[0].read_bytes(), b"existing")
        self.assertTrue(all(not resource.file and resource.external_url for resource in resources))


class ViewerCompatibilityTests(SimpleTestCase):
    def make_asset(self, preferred_format):
        asset = Mock(pk=1, preferred_viewer_format=preferred_format)
        return asset

    def test_requires_every_resource_of_the_preferred_format(self):
        for is_cors_allowed in (True, False):
            with self.subTest(is_cors_allowed=is_cors_allowed):
                preferred = Mock(is_cors_allowed=is_cors_allowed)
                self.assertIs(Asset.calc_is_viewer_compatible(self.make_asset(preferred)), is_cors_allowed)

    def test_ignores_other_formats(self):
        asset = self.make_asset(Mock(is_cors_allowed=False))
        asset.format_set.all.return_value = [Mock(root_resource=Mock(file="poly/model.obj", is_cors_allowed=True))]
        self.assertFalse(Asset.calc_is_viewer_compatible(asset))

    def test_no_preferred_format_or_root(self):
        self.assertFalse(Asset.calc_is_viewer_compatible(self.make_asset(None)))
        self.assertFalse(Asset.calc_is_viewer_compatible(self.make_asset(Mock(root_resource=None))))
