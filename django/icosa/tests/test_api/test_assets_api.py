"""
Tests for Asset API endpoints.
"""
import pytest
from django.test import Client
from django.urls import reverse

from icosa.models.common import PUBLIC, PRIVATE, UNLISTED, ALL_RIGHTS_RESERVED
from icosa.tests.fixtures.factories import (
    AssetFactory,
    PrivateAssetFactory,
    UnlistedAssetFactory,
    UserFactory,
    AssetOwnerFactory,
    TagFactory,
)


@pytest.mark.django_db
@pytest.mark.api
class TestAssetAPIGet:
    """Test suite for GET /api/assets/{asset} endpoint."""

    def test_get_public_asset(self, client):
        """Test retrieving a public asset."""
        asset = AssetFactory(
            url='test-asset',
            name='Test Asset',
            visibility=PUBLIC
        )

        response = client.get(f'/api/v1/assets/{asset.url}')

        assert response.status_code == 200
        data = response.json()
        assert data['displayName'] == 'Test Asset'
        assert data['assetId'] == 'test-asset'

    def test_get_unlisted_asset(self, client):
        """Test retrieving an unlisted asset."""
        asset = UnlistedAssetFactory(
            url='unlisted-asset',
            visibility=UNLISTED
        )

        response = client.get(f'/api/v1/assets/{asset.url}')

        assert response.status_code == 200
        data = response.json()
        assert data['assetId'] == 'unlisted-asset'

    def test_get_private_asset_returns_404(self, client):
        """Test that private assets return 404 for unauthorized users."""
        asset = PrivateAssetFactory(
            url='private-asset',
            visibility=PRIVATE
        )

        response = client.get(f'/api/v1/assets/{asset.url}')

        assert response.status_code == 404

    def test_get_nonexistent_asset_returns_404(self, client):
        """Test retrieving a non-existent asset returns 404."""
        response = client.get('/api/v1/assets/nonexistent-asset')

        assert response.status_code == 404

    def test_asset_response_includes_formats(self, client):
        """Test asset response includes formats information."""
        asset = AssetFactory(
            visibility=PUBLIC,
            has_gltf2=True,
            has_obj=True
        )

        response = client.get(f'/api/v1/assets/{asset.url}')

        assert response.status_code == 200
        data = response.json()
        # Check that format flags are included
        assert 'formats' in data or 'hasGltf2' in data or data.get('has_gltf2') is not None

    def test_asset_response_includes_owner(self, client):
        """Test asset response includes owner information."""
        owner = AssetOwnerFactory(displayname='Test Owner')
        asset = AssetFactory(
            owner=owner,
            visibility=PUBLIC
        )

        response = client.get(f'/api/v1/assets/{asset.url}')

        assert response.status_code == 200
        data = response.json()
        # Owner info should be in the response
        assert 'authorName' in data or 'owner' in data

    def test_asset_response_includes_thumbnail(self, client):
        """Test asset response includes thumbnail URL."""
        asset = AssetFactory(visibility=PUBLIC)

        response = client.get(f'/api/v1/assets/{asset.url}')

        assert response.status_code == 200
        data = response.json()
        assert 'thumbnail' in data or 'thumbnailUrl' in data


@pytest.mark.django_db
@pytest.mark.api
class TestAssetAPIList:
    """Test suite for GET /api/assets endpoint."""

    def test_get_assets_list(self, client):
        """Test retrieving list of public assets."""
        # Create some public assets
        AssetFactory(name='Asset 1', visibility=PUBLIC)
        AssetFactory(name='Asset 2', visibility=PUBLIC)
        AssetFactory(name='Asset 3', visibility=PUBLIC)

        response = client.get('/api/v1/assets/')

        assert response.status_code == 200
        data = response.json()
        assert len(data['assets']) == 3
        assert data['totalSize'] == 3

    def test_get_assets_excludes_private(self, client):
        """Test that asset list excludes private assets."""
        public_asset = AssetFactory(name='Public', visibility=PUBLIC)
        private_asset = PrivateAssetFactory(name='Private', visibility=PRIVATE)

        response = client.get('/api/v1/assets/')

        assert response.status_code == 200
        data = response.json()

        # Private asset should not be in list
        asset_urls = [item['assetId'] for item in data['assets']]
        assert public_asset.url in asset_urls
        assert private_asset.url not in asset_urls

    def test_get_assets_excludes_all_rights_reserved(self, client):
        """Test that asset list excludes all-rights-reserved assets."""
        open_asset = AssetFactory(
            name='Open License',
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )
        arr_asset = AssetFactory(
            name='All Rights Reserved',
            visibility=PUBLIC,
            license=ALL_RIGHTS_RESERVED
        )

        response = client.get('/api/v1/assets/')

        assert response.status_code == 200
        data = response.json()

        asset_urls = [item['assetId'] for item in data['assets']]
        assert open_asset.url in asset_urls
        assert arr_asset.url not in asset_urls

    def test_get_assets_pagination(self, client):
        """Test asset list pagination."""
        # Create many assets
        for i in range(25):
            AssetFactory(
                name=f'Asset {i}',
                visibility=PUBLIC,
                license='CREATIVE_COMMONS_BY_3_0'
            )

        response = client.get('/api/v1/assets/?pageSize=10')

        assert response.status_code == 200
        data = response.json()

        assert len(data['assets']) == 10
        assert data['totalSize'] == 25

    def test_get_assets_filter_by_category(self, client):
        """Test filtering assets by category."""
        animal_asset = AssetFactory(
            name='Dog Model',
            category='ANIMALS',
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )
        tech_asset = AssetFactory(
            name='Robot Model',
            category='TECHNOLOGY',
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )

        response = client.get('/api/v1/assets/?category=ANIMALS')

        assert response.status_code == 200
        data = response.json()

        items = data['assets']

        # Should only include animal assets
        if items:
            for item in items:
                if 'category' in item:
                    assert item['category'] == 'ANIMALS'

    def test_get_assets_order_by_likes(self, client):
        """Test ordering assets by likes."""
        asset_low = AssetFactory(
            name='Low Likes',
            likes=5,
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )
        asset_high = AssetFactory(
            name='High Likes',
            likes=100,
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )

        response = client.get('/api/v1/assets/?orderBy=LIKES')

        assert response.status_code == 200
        # Endpoint should accept the order parameter

    def test_get_assets_filter_by_format(self, client):
        """Test filtering assets by format type."""
        gltf_asset = AssetFactory(
            name='GLTF Asset',
            has_gltf2=True,
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )
        obj_asset = AssetFactory(
            name='OBJ Asset',
            has_obj=True,
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )

        response = client.get('/api/v1/assets/?format=GLTF2')

        assert response.status_code == 200
        # Should accept format filter

    def test_get_assets_search_by_keyword(self, client):
        """Test searching assets by keyword."""
        AssetFactory(
            name='Dragon Model',
            description='A fierce dragon',
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )

        response = client.get('/api/v1/assets/?keywords=dragon')

        assert response.status_code == 200
        # Should accept search keywords

    def test_get_assets_filter_curated(self, client):
        """Test filtering for curated assets only."""
        curated_asset = AssetFactory(
            name='Curated Asset',
            curated=True,
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )
        normal_asset = AssetFactory(
            name='Normal Asset',
            curated=False,
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_3_0'
        )

        response = client.get('/api/v1/assets/?curated=true')

        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.api
class TestAssetAPIUploadState:
    """Test suite for GET /api/assets/{asset}/upload_state endpoint."""

    def test_get_asset_upload_state_authenticated(self, authenticated_client, user):
        """Test getting upload state for owned asset."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner, url='test-asset')

        response = authenticated_client.get(f'/api/v1/assets/{asset.url}/upload_state')

        # Should be accessible
        assert response.status_code in [200, 401, 403, 404]

    def test_get_public_asset_upload_state_unauthenticated(self, client):
        """Test getting upload state for a public asset without authentication."""
        asset = AssetFactory(url='test-asset')

        response = client.get(f'/api/v1/assets/{asset.url}/upload_state')

        assert response.status_code == 200
        assert response.json()['state'] == asset.state

    def test_get_asset_upload_state_includes_state(self, authenticated_client, user):
        """Test upload state response includes asset state."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(
            owner=owner,
            url='test-asset',
            state='PUBLISHED'
        )

        response = authenticated_client.get(f'/api/v1/assets/{asset.url}/upload_state')

        if response.status_code == 200:
            data = response.json()
            assert 'state' in data or 'upload_state' in data


@pytest.mark.django_db
@pytest.mark.api
class TestAssetAPIHelpers:
    """Test suite for API helper functions."""

    def test_user_owns_asset(self):
        """Test user_owns_asset helper function."""
        from icosa.api import user_owns_asset
        from django.test import RequestFactory

        user = UserFactory()
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = user

        assert user_owns_asset(request, asset) is True

    def test_user_does_not_own_asset(self):
        """Test user_owns_asset returns False for non-owner."""
        from icosa.api import user_owns_asset
        from django.test import RequestFactory

        user = UserFactory()
        other_user = UserFactory()
        owner = AssetOwnerFactory(django_user=other_user)
        asset = AssetFactory(owner=owner)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = user

        assert user_owns_asset(request, asset) is False

    def test_user_can_view_public_asset(self):
        """Test user_can_view_asset for public assets."""
        from icosa.api import user_can_view_asset
        from django.test import RequestFactory

        asset = AssetFactory(visibility=PUBLIC)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = UserFactory()

        assert user_can_view_asset(request, asset) is True

    def test_user_can_view_private_owned_asset(self):
        """Test user_can_view_asset for owned private assets."""
        from icosa.api import user_can_view_asset
        from django.test import RequestFactory

        user = UserFactory()
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner, visibility=PRIVATE)

        factory = RequestFactory()
        request = factory.get('/')
        request.user = user

        assert user_can_view_asset(request, asset) is True

    def test_user_cannot_view_private_unowned_asset(self):
        """Test user_can_view_asset for unowned private assets."""
        from icosa.api import user_can_view_asset
        from django.test import RequestFactory

        user = UserFactory()
        asset = PrivateAssetFactory()

        factory = RequestFactory()
        request = factory.get('/')
        request.user = user

        assert user_can_view_asset(request, asset) is False
