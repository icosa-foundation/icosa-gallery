from contextlib import nullcontext
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.parse import urljoin

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import SimpleTestCase
from huey.exceptions import CancelExecution
import requests

from icosa.models import Asset, Format, Resource
from icosa.models.format import (
    ExternalResourceLocalizeException,
    format_cors_cache_key,
    is_permanent_localize_error,
)
from icosa.models.helpers import download_to_tempfile
from icosa.tasks import queue_localize_format


class ExternalLocalizationTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.storage = FileSystemStorage(location=directory.name)
        self.enterContext(patch.object(Resource._meta.get_field("file"), "storage", self.storage))
        self.enterContext(patch("icosa.models.format.get_cloud_media_root", return_value=""))
        self.enterContext(patch("icosa.models.format.get_cached_cors_allow_list", return_value=[]))
        self.delete_many = self.enterContext(patch("icosa.models.format.cache.delete_many"))
        self.enterContext(patch("icosa.models.format.transaction.atomic", side_effect=nullcontext))
        self.enterContext(
            patch("icosa.models.format.download_to_tempfile", side_effect=lambda *args, **kwargs: BytesIO(b"content"))
        )

    def make_format(self, root_url, *resource_urls):
        resources = [Resource(pk=i, external_url=url) for i, url in enumerate([root_url, *resource_urls], start=1)]
        for resource in resources:
            resource.save = Mock()
        format = Mock(pk=1, format_type="GLTF2", root_resource=resources[0], zip_archive_url=None)
        format.asset.owner_id = 2
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
        texture.save.assert_called_once_with(update_fields=["file", "uploaded_file_path", "external_url"])

    def test_archive_org_urls_preserve_layout(self):
        for prefix in (
            "https://web.archive.org/web/https://poly.googleusercontent.com/downloads/x",
            "https://web.archive.org/web/20250101010101id_/https://poly.googleusercontent.com/downloads/x",
        ):
            with self.subTest(prefix=prefix):
                format, (root, texture, sibling) = self.make_format(
                    f"{prefix}/models/model.gltf",
                    f"{prefix}/models/textures/albedo.png",
                    f"{prefix}/shared/model.bin",
                )

                Format.localize_external_resources(format)

                self.assertEqual(root.uploaded_file_path, "models/model.gltf")
                self.assertEqual(texture.uploaded_file_path, "models/textures/albedo.png")
                self.assertEqual(sibling.uploaded_file_path, "shared/model.bin")
                self.assertEqual(urljoin(root.file.name, "textures/albedo.png"), texture.file.name)
                self.assertEqual(urljoin(root.file.name, "../shared/model.bin"), sibling.file.name)
                for resource in (root, texture, sibling):
                    self.storage.delete(resource.file.name)

    def test_ownerless_asset_is_refused_before_downloading(self):
        format, resources = self.make_format("https://example.com/asset/model.gltf")
        format.asset.owner_id = None

        with patch("icosa.models.format.download_to_tempfile") as download:
            with self.assertRaisesRegex(ExternalResourceLocalizeException, "has no owner"):
                Format.localize_external_resources(format)

        download.assert_not_called()

    def test_descendant_paths_keep_original_names(self):
        format, (root, texture) = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/textures/base%20color.png?download=1"
        )

        Format.localize_external_resources(format)

        self.assertEqual(root.uploaded_file_path, "model.gltf")
        self.assertEqual(texture.uploaded_file_path, "textures/base color.png")
        self.assertEqual(urljoin(root.file.name, "textures/base color.png"), texture.file.name)

    def test_resources_outside_root_directory_are_skipped(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf", "https://cdn.example.net/asset/texture.png"
        )

        with self.assertRaisesRegex(ExternalResourceLocalizeException, "not under the root"):
            Format.localize_external_resources(format)

        self.assert_storage_empty()
        self.assertTrue(all(not resource.file and resource.external_url for resource in resources))

    def test_duplicate_urls_share_one_upload(self):
        format, (root, first, second) = self.make_format(
            "https://example.com/asset/model.gltf",
            "https://example.com/asset/texture.png",
            "https://example.com/asset/texture.png",
        )

        with patch("icosa.models.format.download_to_tempfile", side_effect=lambda *a, **k: BytesIO(b"x")) as download:
            Format.localize_external_resources(format)

        self.assertEqual(download.call_count, 2)
        self.assertEqual(first.file.name, second.file.name)
        self.assertIsNone(second.external_url)

    def test_fragment_is_stripped_from_stored_name(self):
        format, (root, texture) = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png#v2"
        )

        Format.localize_external_resources(format)

        self.assertEqual(texture.uploaded_file_path, "texture.png")

    def make_local_root_format(self):
        format, (root, bin_resource) = self.make_format(
            "https://example.com/asset/x/model.gltf", "https://example.com/asset/x/model.bin"
        )
        root.file.name = "poly/A/model_(GLTFupdated).gltf"
        return format, root, bin_resource

    def test_local_root_links_resources_alongside_it(self):
        format, root, bin_resource = self.make_local_root_format()
        self.storage.save("poly/A/model.bin", ContentFile(b"updated"))

        with patch("icosa.models.format.download_to_tempfile") as download:
            self.assertEqual(Format.localize_external_resources(format), [bin_resource])

        download.assert_not_called()
        self.assertEqual(bin_resource.file.name, "poly/A/model.bin")
        self.assertEqual(bin_resource.uploaded_file_path, "model.bin")
        self.assertIsNone(bin_resource.external_url)
        self.assertIsNone(root.external_url)
        root.save.assert_called_once_with(update_fields=["external_url"])
        self.assertEqual(root.get_base_path(), "poly/A/")

    def test_local_root_with_missing_file_alongside_is_refused(self):
        format, root, bin_resource = self.make_local_root_format()

        with self.assertRaisesRegex(ExternalResourceLocalizeException, "does not exist alongside"):
            Format.localize_external_resources(format)

        self.assertFalse(bin_resource.file)
        self.assertIsNotNone(bin_resource.external_url)
        self.assertIsNotNone(root.external_url)
        self.assert_storage_empty()

    def test_cors_cache_is_cleared_for_every_resource(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png"
        )

        Format.localize_external_resources(format)

        keys = self.delete_many.call_args.args[0]
        self.assertIn("resource_is_cors_allowed-1-[]", keys)
        self.assertIn("resource_is_cors_allowed-2-[]", keys)
        self.assertIn("format_is_cors_allowed-1-1-2-[]", keys)

    def test_cors_cache_is_cleared_when_nothing_is_left_to_do(self):
        format, (root,) = self.make_format("https://example.com/asset/model.gltf")
        root.file.name = "poly/model.gltf"
        root.external_url = None

        self.assertEqual(Format.localize_external_resources(format), [])

        self.assertIn("format_is_cors_allowed-1-1-[]", self.delete_many.call_args.args[0])

    def test_format_cors_cache_key_ignores_resource_order(self):
        self.assertEqual(format_cors_cache_key(1, [3, 2], "x"), format_cors_cache_key(1, [2, 3], "x"))

    def test_local_resources_clear_external_archive(self):
        format, (root,) = self.make_format("https://example.com/asset/model.gltf")
        root.file.name = "poly/model.gltf"
        format.zip_archive_url = "https://example.com/asset/archive.zip"

        self.assertEqual(Format.localize_external_resources(format), [])

        self.assertIsNone(format.zip_archive_url)
        format.save.assert_called_once_with(update_fields=["zip_archive_url"], update_timestamps=False)

    def assert_storage_empty(self):
        self.assertEqual([path for path in Path(self.storage.location).rglob("*") if path.is_file()], [])

    def test_archive_is_kept_when_there_are_no_resources(self):
        format = Mock(pk=1, format_type="GLTF2", root_resource=None, zip_archive_url="https://example.com/archive.zip")
        format.asset.owner_id = 2
        format.asset.id = 3
        format.resource_set.all.return_value = []

        self.assertEqual(Format.localize_external_resources(format), [])

        self.assertEqual(format.zip_archive_url, "https://example.com/archive.zip")
        format.save.assert_not_called()

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

    def test_interrupted_upload_removes_files(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png"
        )
        save = self.storage.save
        saves = 0

        def interrupt_second_upload(*args, **kwargs):
            nonlocal saves
            saves += 1
            if saves == 2:
                raise KeyboardInterrupt
            return save(*args, **kwargs)

        with patch.object(self.storage, "save", side_effect=interrupt_second_upload):
            with self.assertRaises(KeyboardInterrupt):
                Format.localize_external_resources(format)

        self.assert_storage_empty()

    def test_failed_cleanup_delete_continues_and_reraises_original_error(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf",
            "https://example.com/asset/a.png",
            "https://example.com/asset/b.png",
        )
        save = self.storage.save
        delete = self.storage.delete
        saves = 0

        def fail_third_upload(*args, **kwargs):
            nonlocal saves
            saves += 1
            if saves == 3:
                raise OSError("Upload failed")
            return save(*args, **kwargs)

        def fail_first_delete(name):
            if name.endswith("a.png"):
                raise OSError("Delete failed")
            delete(name)

        with patch.object(self.storage, "save", side_effect=fail_third_upload):
            with patch.object(self.storage, "delete", side_effect=fail_first_delete):
                with self.assertRaisesRegex(OSError, "Upload failed"):
                    Format.localize_external_resources(format)

        remaining = [path.name for path in Path(self.storage.location).rglob("*") if path.is_file()]
        self.assertEqual(remaining, ["a.png"])

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

    def test_existing_directory_is_never_written_into(self):
        format, (root, texture) = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png"
        )
        existing_name = self.storage.save("2/3/GLTF2/model.gltf", ContentFile(b"existing"))
        Path(self.storage.path("2/3/GLTF2_2")).mkdir()

        Format.localize_external_resources(format)

        self.assertEqual(root.file.name, "2/3/GLTF2_3/model.gltf")
        self.assertEqual(texture.file.name, "2/3/GLTF2_3/texture.png")
        self.assertEqual(Path(self.storage.path(existing_name)).read_bytes(), b"existing")

    def test_storage_renaming_a_file_removes_new_files(self):
        format, resources = self.make_format(
            "https://example.com/asset/model.gltf", "https://example.com/asset/texture.png"
        )
        save = self.storage.save

        def rename(name, content, **kwargs):
            return save(f"{name}.renamed", content, **kwargs)

        with patch.object(self.storage, "save", side_effect=rename):
            with self.assertRaises(ExternalResourceLocalizeException):
                Format.localize_external_resources(format)

        self.assert_storage_empty()
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


class DownloadRetryTests(SimpleTestCase):
    def download(self, error):
        with patch("icosa.models.helpers.requests.get", side_effect=error) as get:
            with patch("icosa.models.helpers.time.sleep"):
                with self.assertRaises(type(error)):
                    download_to_tempfile("https://example.com/model.gltf", retries=2)
        return get.call_count

    def http_error(self, status):
        return requests.HTTPError(response=Mock(status_code=status))

    def test_transient_errors_are_retried(self):
        for error in (requests.ConnectionError(), requests.Timeout(), self.http_error(429), self.http_error(503)):
            with self.subTest(error=error):
                self.assertEqual(self.download(error), 3)

    def test_permanent_errors_are_not_retried(self):
        for error in (requests.exceptions.MissingSchema(), requests.exceptions.InvalidURL(), self.http_error(404)):
            with self.subTest(error=error):
                self.assertEqual(self.download(error), 1)



class PermanentLocalizeErrorTests(SimpleTestCase):
    def test_permanent_errors(self):
        for error in (
            Format.DoesNotExist(),
            ExternalResourceLocalizeException("refused"),
            requests.HTTPError(response=Mock(status_code=404)),
            requests.exceptions.InvalidURL(),
        ):
            with self.subTest(error=error):
                self.assertTrue(is_permanent_localize_error(error))

    def test_transient_or_unknown_errors(self):
        for error in (requests.ConnectionError(), requests.HTTPError(response=Mock(status_code=503)), OSError()):
            with self.subTest(error=error):
                self.assertFalse(is_permanent_localize_error(error))


class LocalizeTaskRetryTests(SimpleTestCase):
    def run_task(self, error):
        with patch("icosa.tasks.localize_format", side_effect=error):
            queue_localize_format.call_local(1)

    def test_permanent_failures_cancel_retries(self):
        with self.assertRaises(CancelExecution) as cm:
            self.run_task(requests.HTTPError(response=Mock(status_code=404)))
        self.assertIs(cm.exception.retry, False)

    def test_transient_failures_propagate_for_retry(self):
        with self.assertRaises(requests.ConnectionError):
            self.run_task(requests.ConnectionError())
