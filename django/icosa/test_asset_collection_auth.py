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
            django_user=self.alice,
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            displayname="Bob",
        )
        self.bob_owner = AssetOwner.objects.create(
            url="bob",
            displayname="Bob",
            django_user=self.bob,
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
            user=self.alice,
            url="alice-private",
            name="Alice private",
            visibility=PRIVATE,
        )
        public_collection = AssetCollection.objects.create(
            user=self.alice,
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
            user=self.alice,
            url="visible-public",
            name="Visible public collection",
            visibility=PUBLIC,
        )
        AssetCollection.objects.create(
            user=self.alice,
            url="unlisted",
            name="Unlisted collection",
            visibility=UNLISTED,
        )
        rejected_collection = AssetCollection.objects.create(
            user=self.alice,
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
            user=self.alice,
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
            user=self.alice,
            url="api-visible",
            name="API visible",
            visibility=PUBLIC,
        )
        AssetCollection.objects.create(
            user=self.alice,
            url="api-unlisted",
            name="API unlisted",
            visibility=UNLISTED,
        )
        AssetCollection.objects.create(
            user=self.alice,
            url="api-archived",
            name="API archived",
            visibility=ARCHIVED,
        )
        rejected = AssetCollection.objects.create(
            user=self.alice,
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
        collection = AssetCollection.objects.get(user=self.alice)
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

    def test_user_cannot_edit_or_delete_another_users_collection(self):
        collection = AssetCollection.objects.create(
            user=self.alice,
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
            user=self.alice,
            url="public-index",
            name="Public index collection",
            visibility=PUBLIC,
        )
        private_collection = AssetCollection.objects.create(
            user=self.alice,
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

    @override_settings(PAGINATION_PER_PAGE=1)
    def test_public_collection_index_paginates(self):
        older_collection = AssetCollection.objects.create(
            user=self.alice,
            url="older-public-index",
            name="Older public collection",
            visibility=PUBLIC,
        )
        newer_collection = AssetCollection.objects.create(
            user=self.alice,
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
