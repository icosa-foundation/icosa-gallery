import io
import zipfile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from icosa.api.exceptions import ZipException
from icosa.forms import CollectionZipUploadForm
from icosa.helpers.upload_web_ui import (
    analyze_collection_zip,
    upload_collection_from_zip,
)
from icosa.models import (
    ASSET_STATE_COMPLETE,
    PRIVATE,
    Asset,
    AssetCollection,
    AssetOwner,
    Format,
    User,
)
from icosa.tasks import queue_upload_collection_from_zip


class CollectionZipImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="zip-importer",
            email="zip-importer@example.com",
            displayname="ZIP Importer",
        )
        self.owner = AssetOwner.objects.create(
            url="zip-importer",
            displayname="ZIP Importer",
            django_user=self.user,
        )
        self.static_collection = AssetCollection.objects.create(
            owner=self.owner,
            name="Static target",
            visibility=PRIVATE,
        )
        self.dynamic_collection = AssetCollection.objects.create(
            owner=self.owner,
            name="Dynamic target",
            visibility=PRIVATE,
            query_parameters={"category": "ANIMALS"},
        )

    def test_form_only_offers_static_collections_owned_by_user(self):
        queryset = CollectionZipUploadForm(
            user=self.user
        ).fields["existing_collection"].queryset

        self.assertEqual(list(queryset), [self.static_collection])

    def test_service_rejects_dynamic_collection_even_if_form_is_bypassed(self):
        with self.assertRaises(ValidationError):
            upload_collection_from_zip(
                user=self.user,
                owner=self.owner,
                zip_file=SimpleUploadedFile("assets.zip", b""),
                existing_collection=self.dynamic_collection,
            )

    def test_zip_structure_groups_root_stems_and_top_level_directories(self):
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("root-model.glb", b"model")
            archive.writestr("root-model.png", b"thumbnail")
            archive.writestr("folder/model.gltf", b"model")
            archive.writestr("folder/model.bin", b"binary")
            archive.writestr("folder/thumbnail.jpg", b"thumbnail")
        archive_data.seek(0)

        with zipfile.ZipFile(archive_data) as archive:
            structure = analyze_collection_zip(archive)

        self.assertEqual(
            structure,
            {
                "root-model": {
                    "files": ["root-model.glb"],
                    "thumbnail": "root-model.png",
                },
                "folder": {
                    "files": ["folder/model.gltf", "folder/model.bin"],
                    "thumbnail": "folder/thumbnail.jpg",
                },
            },
        )

    def test_import_creates_static_collection_owned_by_asset_owner(self):
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("example.glb", b"model")
        uploaded_archive = SimpleUploadedFile(
            "assets.zip",
            archive_data.getvalue(),
        )

        def fake_async_to_sync(async_function):
            def fake_upload(asset, *args, **kwargs):
                Format.objects.create(asset=asset, format_type="GLB")
                asset.state = ASSET_STATE_COMPLETE
                asset.save()
                return asset

            return fake_upload

        with patch(
            "icosa.helpers.upload_web_ui.async_to_sync",
            side_effect=fake_async_to_sync,
        ):
            collection = upload_collection_from_zip(
                user=self.user,
                owner=self.owner,
                zip_file=uploaded_archive,
                collection_name="Imported collection",
            )

        self.assertEqual(collection.owner, self.owner)
        self.assertFalse(collection.is_dynamic)
        self.assertEqual(collection.name, "Imported collection")
        self.assertEqual(
            list(collection.assets.values_list("name", flat=True)),
            ["example"],
        )

    def test_oversized_zip_is_rejected_before_creating_assets(self):
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("example.glb", b"oversized model")

        with patch(
            "icosa.helpers.upload_web_ui.MAX_UNZIP_BYTES", 4
        ), self.assertRaises(ZipException):
            upload_collection_from_zip(
                user=self.user,
                owner=self.owner,
                zip_file=SimpleUploadedFile(
                    "assets.zip",
                    archive_data.getvalue(),
                ),
                collection_name="Rejected collection",
            )

        self.assertFalse(Asset.objects.exists())
        self.assertFalse(
            AssetCollection.objects.filter(name="Rejected collection").exists()
        )

    def test_queued_upload_stages_zip_in_storage(self):
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr("example.glb", b"model")

        self.client.force_login(self.user)
        with TemporaryDirectory() as media_root, override_settings(
            ENABLE_TASK_QUEUE=True,
            MEDIA_ROOT=media_root,
        ), patch("icosa.views.main.queue_upload_collection_from_zip") as queue:
            response = self.client.post(
                reverse("icosa:upload_collection"),
                {
                    "collection_zip": SimpleUploadedFile(
                        "assets.zip",
                        archive_data.getvalue(),
                        content_type="application/zip",
                    ),
                    "collection_name": "Queued collection",
                    "visibility": PRIVATE,
                },
            )

            self.assertEqual(response.status_code, 200)
            zip_storage_name = queue.call_args.kwargs["zip_storage_name"]
            self.assertIsInstance(zip_storage_name, str)
            self.assertTrue(default_storage.exists(zip_storage_name))
            default_storage.delete(zip_storage_name)

    def test_queued_upload_deletes_staged_zip_after_failure(self):
        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            zip_storage_name = default_storage.save(
                "queued_collection_uploads/test.zip",
                SimpleUploadedFile("test.zip", b"not a zip"),
            )
            with patch(
                "icosa.helpers.upload_web_ui.upload_collection_from_zip",
                side_effect=RuntimeError("import failed"),
            ), self.assertRaises(RuntimeError):
                queue_upload_collection_from_zip.call_local(
                    user_id=self.user.pk,
                    owner_id=self.owner.pk,
                    zip_storage_name=zip_storage_name,
                    collection_name="Failed collection",
                )

            self.assertFalse(default_storage.exists(zip_storage_name))
