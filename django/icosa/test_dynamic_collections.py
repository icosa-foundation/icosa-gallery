from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from icosa.api.filters import FilterLicense, FiltersAsset
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
            django_user=self.user,
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

    def test_featured_dynamic_collections_are_seeded(self):
        expected_queries = {
            settings.OPEN_BRUSH_COLLECTION_URL: {
                "format": ["TILT"],
                "curated": True,
                "orderBy": "BEST",
            },
            settings.OPEN_BLOCKS_COLLECTION_URL: {
                "filter": "(authorId=4aEd8rQgKu2)|(format=BLOCKS,curated=true)",
                "orderBy": "BEST",
            },
        }

        collections = AssetCollection.objects.filter(
            url__in=expected_queries,
            owner__url="icosa-gallery",
            visibility=PUBLIC,
            markdown=True,
        )

        self.assertEqual(collections.count(), 2)
        for collection in collections:
            self.assertEqual(
                collection.query_parameters,
                expected_queries[collection.url],
            )

    def test_dynamic_collection_uses_public_asset_query_filters(self):
        self.assertEqual(
            list(self.collection.get_public_assets()),
            [self.matching_asset],
        )

    def test_remixable_excludes_licenses_with_downstream_restrictions(self):
        restricted_licenses = [
            "CREATIVE_COMMONS_BY_SA_4_0",
            "CREATIVE_COMMONS_NC_4_0",
            "CREATIVE_COMMONS_NC_SA_4_0",
        ]
        for index, license_name in enumerate(restricted_licenses):
            Asset.objects.create(
                url=f"restricted-remix-{index}",
                name="Restricted remix",
                owner=self.owner,
                visibility=PUBLIC,
                license=license_name,
            )

        remixable_query = FiltersAsset().filter_license(FilterLicense.REMIXABLE)

        self.assertCountEqual(
            Asset.objects.filter(remixable_query, visibility=PUBLIC).values_list(
                "url", flat=True
            ),
            ["matching-asset", "nonmatching-asset"],
        )

    def test_dynamic_collection_supports_or_filter_groups(self):
        self.collection.query_parameters = {
            "filter": "(category=ANIMALS)|(category=TECH,curated=false)"
        }
        self.collection.full_clean()

        self.assertEqual(
            list(self.collection.get_public_assets()),
            [self.matching_asset],
        )

    def test_flat_filters_are_anded_with_or_filter_groups(self):
        self.collection.query_parameters = {
            "curated": True,
            "filter": "(category=ANIMALS)|(category=TECH)",
        }

        self.assertCountEqual(
            self.collection.get_public_assets(),
            [self.matching_asset, self.nonmatching_asset],
        )

    def test_asset_api_accepts_the_same_or_filter_syntax(self):
        response = self.client.get(
            "/api/v1/assets",
            {"filter": "(category=ANIMALS)|(category=TECH,curated=false)"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [asset["assetId"] for asset in response.json()["assets"]],
            [self.matching_asset.url],
        )

    def test_asset_api_accepts_url_decoded_commas_in_filter_values(self):
        comma_asset = Asset.objects.create(
            url="comma-name",
            name="Smith, John",
            owner=self.owner,
            visibility=PUBLIC,
            license="CREATIVE_COMMONS_0",
            create_time=timezone.now(),
        )

        response = self.client.get(
            "/api/v1/assets?filter=%28name%3DSmith%2C%20John%29"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [asset["assetId"] for asset in response.json()["assets"]],
            [comma_asset.url],
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

    def test_invalid_or_filter_expression_is_rejected(self):
        self.collection.query_parameters = {
            "filter": "(category=ANIMALS)|(unsupported=value)"
        }

        with self.assertRaises(ValidationError):
            self.collection.full_clean()

    def test_asset_api_rejects_invalid_or_filter_syntax(self):
        response = self.client.get(
            "/api/v1/assets",
            {"filter": "(category=ANIMALS)|(unsupported=value)"},
        )

        self.assertEqual(response.status_code, 400)

    def test_markdown_description_disables_raw_html(self):
        self.collection.description = "**Safe** <script>alert('unsafe')</script>"
        self.collection.markdown = True
        self.collection.save()

        response = self.client.get(self.collection.get_absolute_url())

        self.assertContains(response, "<strong>Safe</strong>", html=True)
        self.assertNotContains(response, "<script>alert('unsafe')</script>")
        self.assertContains(
            response,
            "&lt;script&gt;alert('unsafe')&lt;/script&gt;",
        )

    def test_legacy_routes_redirect_to_collection(self):
        routes = {
            "icosa:home_openbrush": settings.OPEN_BRUSH_COLLECTION_URL,
            "icosa:home_blocks": settings.OPEN_BLOCKS_COLLECTION_URL,
        }
        for route_name, collection_url in routes.items():
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertRedirects(
                    response,
                    reverse(
                        "icosa:asset_collection_view",
                        kwargs={"collection_url": collection_url},
                    ),
                    status_code=302,
                    fetch_redirect_response=False,
                )
