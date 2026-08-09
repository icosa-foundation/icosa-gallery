from django.test import TestCase
from django.urls import reverse

from icosa.models import PUBLIC, AssetCollection, AssetOwner, FeaturedCollection


class FeaturedCollectionsTests(TestCase):
    def setUp(self):
        owner = AssetOwner.objects.get(url="icosa-gallery")
        self.first_collection = AssetCollection.objects.create(
            owner=owner,
            url="first-featured",
            name="First Featured",
            visibility=PUBLIC,
        )
        self.second_collection = AssetCollection.objects.create(
            owner=owner,
            url="second-featured",
            name="Second Featured",
            visibility=PUBLIC,
        )

    def test_sidebar_lists_configured_collections_in_order(self):
        FeaturedCollection.objects.create(
            collection=self.second_collection,
            order=20,
        )
        FeaturedCollection.objects.create(
            collection=self.first_collection,
            order=10,
        )

        response = self.client.get(reverse("icosa:home"))
        content = response.content.decode()

        self.assertContains(response, "Featured Collections")
        self.assertContains(response, self.first_collection.get_absolute_url())
        self.assertContains(response, self.second_collection.get_absolute_url())
        self.assertLess(
            content.index(self.first_collection.name),
            content.index(self.second_collection.name),
        )

    def test_sidebar_hides_empty_featured_collection_section(self):
        response = self.client.get(reverse("icosa:home"))

        self.assertNotContains(response, "Featured Collections")
