from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from icosa.models import (
    PRIVATE,
    PUBLIC,
    Asset,
    AssetCollection,
    AssetCollectionAsset,
    AssetOwner,
    User,
)


class DynamicCollectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="curator",
            email="curator@example.com",
            displayname="Curator",
        )
        self.owner = AssetOwner.objects.create(
            url="curator",
            displayname="Curator",
            django_owner=self.owner,
        )
        self.matching_asset = Asset.objects.create(
            url="matching-asset",
            name="Matching asset",
            owner=self.owner,
            visibility=PUBLIC,
            category="ANIMALS",
            curated=True,
            license="CREATIVE_COMMONS_0",
            create_time=timezone.now(),
        )
        self.nonmatching_asset = Asset.objects.create(
            url="nonmatching-asset",
            name="Nonmatching asset",
            owner=self.owner,
            visibility=PUBLIC,
            category="TECH",
            curated=True,
            license="CREATIVE_COMMONS_0",
            create_time=timezone.now(),
        )
        self.private_asset = Asset.objects.create(
            url="private-asset",
            name="Private asset",
            owner=self.owner,
            visibility=PRIVATE,
            category="ANIMALS",
            curated=True,
            license="CREATIVE_COMMONS_0",
            create_time=timezone.now(),
        )
        self.collection = AssetCollection.objects.create(
            owner=self.owner,
            url="animals",
            name="Animals",
            visibility=PUBLIC,
            query_parameters={"category": "ANIMALS", "curated": True},
        )

    def test_dynamic_collection_uses_public_asset_query_filters(self):
        self.assertEqual(
            list(self.collection.get_public_assets()),
            [self.matching_asset],
        )

    def test_dynamic_collection_rejects_explicit_assets(self):
        item = AssetCollectionAsset(
            collection=self.collection,
            asset=self.matching_asset,
        )

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_unknown_query_parameters_are_rejected(self):
        self.collection.query_parameters = {"unsupported": True}

        with self.assertRaises(ValidationError):
            self.collection.full_clean()
