import io
import zipfile
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from icosa.forms import CollectionZipUploadForm
from icosa.helpers.upload_web_ui import (
    analyze_collection_zip,
    upload_collection_from_zip,
)
from icosa.models import (
    ASSET_STATE_COMPLETE,
    PRIVATE,
    AssetCollection,
    AssetOwner,
    Format,
    User,
)


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
