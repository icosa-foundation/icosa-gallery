from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from icosa.model_mixins import MOD_REJECTED
from icosa.models import (
    ARCHIVED,
    PRIVATE,
    PUBLIC,
    UNLISTED,
    Asset,
    AssetCollection,
    AssetCollectionAsset,
    AssetOwner,
    User,
)


class AssetCollectionAuthorizationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            displayname="Alice",
        )
        self.alice_owner = AssetOwner.objects.create(
            url="alice",
            displayname="Alice",
            django_owner=self.alice_owner,
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            displayname="Bob",
        )
        self.bob_owner = AssetOwner.objects.create(
            url="bob",
            displayname="Bob",
            django_owner=self.bob_owner,
        )
        self.public_asset = Asset.objects.create(
            url="public-asset",
            name="Public asset",
            owner=self.alice_owner,
            visibility=PUBLIC,
            create_time=timezone.now(),
        )

    def test_anonymous_user_cannot_create_a_collection(self):
        response = self.client.post(
            self.collection_list_url(self.alice_owner),
            {
                "asset_url": self.public_asset.url,
                "new-collection-name": "Anonymous collection",
                "_add_to_new_collection": "Create and add",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('icosa:login')}?next={self.collection_list_url(self.alice_owner)}",
            fetch_redirect_response=False,
        )
        self.assertFalse(AssetCollection.objects.exists())

    def test_user_cannot_create_a_collection_without_a_name(self):
        self.client.force_login(self.alice)

        for name in ["", "   "]:
            with self.subTest(name=name):
                response = self.client.post(
                    self.collection_list_url(self.alice_owner),
                    {
                        "asset_url": self.public_asset.url,
                        "new-collection-name": name,
                        "_add_to_new_collection": "Create and add",
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertContains(
                    response,
                    "collection name is required",
                    status_code=400,
                )
                self.assertFalse(AssetCollection.objects.exists())

    def test_user_cannot_create_a_collection_through_another_users_url(self):
        self.client.force_login(self.bob)

        response = self.client.post(
            self.collection_list_url(self.alice_owner),
            {
                "asset_url": self.public_asset.url,
                "new-collection-name": "Wrong owner",
                "_add_to_new_collection": "Create and add",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(AssetCollection.objects.exists())

    def test_user_cannot_add_another_users_private_asset(self):
        private_asset = Asset.objects.create(
            url="private-asset",
            name="Private asset",
            owner=self.alice_owner,
            visibility=PRIVATE,
            create_time=timezone.now(),
        )
        self.client.force_login(self.bob)

        response = self.client.post(
            self.collection_list_url(self.bob_owner),
            {
                "asset_url": private_asset.url,
                "new-collection-name": "Private asset collection",
                "_add_to_new_collection": "Create and add",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(AssetCollection.objects.exists())

    def test_collection_detail_is_scoped_to_the_user_in_the_url(self):
        private_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="alice-private",
            name="Alice private",
            visibility=PRIVATE,
        )
        public_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="alice-public",
            name="Alice public",
            visibility=PUBLIC,
        )
        self.client.force_login(self.bob)

        self.assertEqual(
            self.client.get(
                self.collection_detail_url(self.bob_owner, private_collection)
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                self.collection_detail_url(self.bob_owner, public_collection)
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                self.collection_detail_url(self.alice_owner, private_collection)
            ).status_code,
            404,
        )

    def test_public_list_hides_unlisted_and_moderation_hidden_collections(self):
        public_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="visible-public",
            name="Visible public collection",
            visibility=PUBLIC,
        )
        AssetCollection.objects.create(
            owner=self.alice_owner,
            url="unlisted",
            name="Unlisted collection",
            visibility=UNLISTED,
        )
        rejected_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="rejected",
            name="Rejected collection",
            visibility=PUBLIC,
        )
        AssetCollection.objects.filter(pk=rejected_collection.pk).update(
            moderation_state=MOD_REJECTED
        )

        response = self.client.get(self.collection_list_url(self.alice_owner))

        self.assertContains(response, public_collection.name)
        self.assertNotContains(response, "Unlisted collection")
        self.assertNotContains(response, "Rejected collection")

    def test_unlisted_collection_is_available_only_by_its_canonical_direct_link(self):
        collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="direct-link",
            name="Direct link collection",
            visibility=UNLISTED,
        )

        response = self.client.get(
            self.collection_detail_url(self.alice_owner, collection)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, collection.name)

    def test_public_api_exposes_only_visible_public_collections(self):
        visible = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="api-visible",
            name="API visible",
            visibility=PUBLIC,
        )
        AssetCollection.objects.create(
            owner=self.alice_owner,
            url="api-unlisted",
            name="API unlisted",
            visibility=UNLISTED,
        )
        AssetCollection.objects.create(
            owner=self.alice_owner,
            url="api-archived",
            name="API archived",
            visibility=ARCHIVED,
        )
        rejected = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="api-rejected",
            name="API rejected",
            visibility=PUBLIC,
        )
        AssetCollection.objects.filter(pk=rejected.pk).update(
            moderation_state=MOD_REJECTED
        )

        response = self.client.get(reverse("icosa:api:asset_collection_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [collection["collectionId"] for collection in response.json()["collections"]],
            [visible.url],
        )

    def test_owner_can_create_edit_and_delete_a_collection(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("icosa:asset_collection_create"),
            {
                "name": "New collection",
                "description": "Draft description",
                "visibility": PRIVATE,
            },
        )

        self.assertRedirects(response, reverse("icosa:my_asset_collection_list"))
        collection = AssetCollection.objects.get(owner=self.alice_owner)
        self.assertTrue(collection.url)

        response = self.client.post(
            reverse(
                "icosa:asset_collection_edit",
                kwargs={"collection_url": collection.url},
            ),
            {
                "name": "Published collection",
                "description": "Published description",
                "visibility": PUBLIC,
            },
        )

        collection.refresh_from_db()
        self.assertRedirects(response, collection.get_absolute_url())
        self.assertEqual(collection.name, "Published collection")
        self.assertEqual(collection.visibility, PUBLIC)

        response = self.client.post(
            reverse(
                "icosa:asset_collection_delete",
                kwargs={"collection_url": collection.url},
            )
        )

        self.assertRedirects(response, reverse("icosa:my_asset_collection_list"))
        self.assertFalse(AssetCollection.objects.exists())

    def test_collection_form_uses_an_image_upload_control(self):
        self.client.force_login(self.alice)

        response = self.client.get(reverse("icosa:asset_collection_create"))

        self.assertContains(response, 'type="file"')
        self.assertContains(response, 'accept="image/png,image/jpeg"')
        self.assertNotContains(response, "Use current viewport as the thumbnail")

    def test_owner_can_reorder_and_remove_collection_items(self):
        second_asset = Asset.objects.create(
            url="second-collection-asset",
            name="Second collection asset",
            owner=self.alice_owner,
            visibility=PUBLIC,
            create_time=timezone.now(),
        )
        third_asset = Asset.objects.create(
            url="third-collection-asset",
            name="Third collection asset",
            owner=self.alice_owner,
            visibility=PUBLIC,
            create_time=timezone.now(),
        )
        collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="managed-items",
            name="Managed items",
        )
        first_item = AssetCollectionAsset.objects.create(
            collection=collection,
            asset=self.public_asset,
            order=0,
        )
        second_item = AssetCollectionAsset.objects.create(
            collection=collection,
            asset=second_asset,
            order=1,
        )
        third_item = AssetCollectionAsset.objects.create(
            collection=collection,
            asset=third_asset,
            order=2,
        )
        self.client.force_login(self.alice)
        action_url = reverse(
            "icosa:asset_collection_item_update",
            kwargs={"collection_url": collection.url},
        )

        edit_response = self.client.get(
            reverse(
                "icosa:asset_collection_edit",
                kwargs={"collection_url": collection.url},
            )
        )
        self.assertContains(edit_response, second_asset.name)
        self.assertContains(edit_response, 'value="move_up"')
        self.assertContains(edit_response, 'value="move_down"')
        self.assertContains(edit_response, "Remove")
        self.assertContains(edit_response, "Delete this collection? This cannot be undone.")

        response = self.client.post(
            action_url,
            {"item_id": third_item.pk, "action": "move_up"},
        )
        self.assertRedirects(
            response,
            reverse(
                "icosa:asset_collection_edit",
                kwargs={"collection_url": collection.url},
            ),
        )
        self.assertEqual(
            list(
                collection.collected_assets.order_by("order").values_list(
                    "asset_id",
                    flat=True,
                )
            ),
            [first_item.asset_id, third_item.asset_id, second_item.asset_id],
        )

        self.client.post(
            action_url,
            {"item_id": third_item.pk, "action": "remove"},
        )
        self.assertEqual(
            list(
                collection.collected_assets.order_by("order").values_list(
                    "asset_id",
                    "order",
                )
            ),
            [(first_item.asset_id, 0), (second_item.asset_id, 1)],
        )

    def test_adding_an_asset_appends_it_to_the_collection(self):
        existing_asset = Asset.objects.create(
            url="existing-collection-asset",
            name="Existing collection asset",
            owner=self.alice_owner,
            visibility=PUBLIC,
            create_time=timezone.now(),
        )
        collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="append-items",
            name="Append items",
        )
        AssetCollectionAsset.objects.create(
            collection=collection,
            asset=existing_asset,
            order=0,
        )
        self.client.force_login(self.alice)

        response = self.client.post(
            self.collection_list_url(self.alice_owner),
            {
                "asset_url": self.public_asset.url,
                f"_add_to_collection__{collection.url}": "Add",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(
                collection.collected_assets.order_by("order").values_list(
                    "asset_id",
                    "order",
                )
            ),
            [(existing_asset.pk, 0), (self.public_asset.pk, 1)],
        )

    def test_user_cannot_manage_another_users_collection_items(self):
        collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="alice-managed-items",
            name="Alice managed items",
        )
        item = AssetCollectionAsset.objects.create(
            collection=collection,
            asset=self.public_asset,
        )
        self.client.force_login(self.bob)

        response = self.client.post(
            reverse(
                "icosa:asset_collection_item_update",
                kwargs={"collection_url": collection.url},
            ),
            {"item_id": item.pk, "action": "remove"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(AssetCollectionAsset.objects.filter(pk=item.pk).exists())

    def test_user_cannot_edit_or_delete_another_users_collection(self):
        collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="alice-edit",
            name="Alice collection",
            visibility=PRIVATE,
        )
        self.client.force_login(self.bob)

        edit_url = reverse(
            "icosa:asset_collection_edit",
            kwargs={"collection_url": collection.url},
        )
        delete_url = reverse(
            "icosa:asset_collection_delete",
            kwargs={"collection_url": collection.url},
        )

        self.assertEqual(self.client.get(edit_url).status_code, 404)
        self.assertEqual(self.client.post(edit_url, {}).status_code, 404)
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.assertTrue(AssetCollection.objects.filter(pk=collection.pk).exists())

    def test_collection_indexes_are_discoverable_for_public_and_owner_views(self):
        public_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="public-index",
            name="Public index collection",
            visibility=PUBLIC,
        )
        private_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="private-index",
            name="Private index collection",
            visibility=PRIVATE,
        )

        public_response = self.client.get(reverse("icosa:asset_collection_list"))
        self.assertContains(public_response, public_collection.name)
        self.assertNotContains(public_response, private_collection.name)

        self.client.force_login(self.alice)
        owner_response = self.client.get(reverse("icosa:my_asset_collection_list"))
        self.assertContains(owner_response, public_collection.name)
        self.assertContains(owner_response, private_collection.name)

    def test_profile_assets_and_collections_are_presented_as_tabs(self):
        AssetCollection.objects.create(
            owner=self.alice_owner,
            url="profile-tab-collection",
            name="Profile tab collection",
            visibility=PUBLIC,
        )
        assets_url = reverse(
            "icosa:user_show",
            kwargs={"slug": self.alice_owner.url},
        )
        collections_url = self.collection_list_url(self.alice_owner)

        assets_response = self.client.get(assets_url)
        self.assertContains(
            assets_response,
            f'class="profile-tab active" href="{assets_url}"',
        )
        self.assertContains(
            assets_response,
            f'class="profile-tab" href="{collections_url}"',
        )

        collections_response = self.client.get(collections_url)
        self.assertContains(
            collections_response,
            f'class="profile-tab" href="{assets_url}"',
        )
        self.assertContains(
            collections_response,
            f'class="profile-tab active" href="{collections_url}"',
        )

    @override_settings(PAGINATION_PER_PAGE=1)
    def test_public_collection_index_paginates(self):
        older_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="older-public-index",
            name="Older public collection",
            visibility=PUBLIC,
        )
        newer_collection = AssetCollection.objects.create(
            owner=self.alice_owner,
            url="newer-public-index",
            name="Newer public collection",
            visibility=PUBLIC,
        )

        first_page = self.client.get(reverse("icosa:asset_collection_list"))
        self.assertContains(first_page, newer_collection.name)
        self.assertNotContains(first_page, older_collection.name)
        self.assertContains(first_page, "?page=2")

        second_page = self.client.get(
            reverse("icosa:asset_collection_list"),
            {"page": 2},
        )
        self.assertContains(second_page, older_collection.name)
        self.assertNotContains(second_page, newer_collection.name)

    @staticmethod
    def collection_list_url(owner):
        return reverse(
            "icosa:user_asset_collection_list",
            kwargs={"user_url": owner.url},
        )

    @staticmethod
    def collection_detail_url(owner, collection):
        return reverse(
            "icosa:user_asset_collection_view",
            kwargs={
                "user_url": owner.url,
                "collection_url": collection.url,
            },
        )
