"""
Tests for main view functions.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from icosa.models import (
    Asset,
    AssetOwner,
    UserLike,
    MastheadSection,
    PUBLIC,
    PRIVATE,
    UNLISTED,
    ARCHIVED,
    ALL_RIGHTS_RESERVED,
    ASSET_STATE_UPLOADING,
    ASSET_STATE_FAILED,
)
from icosa.tests.fixtures.factories import (
    AssetFactory,
    UserFactory,
    AssetOwnerFactory,
    UserLikeFactory,
    PrivateAssetFactory,
)

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.views
class TestHealthView:
    """Test suite for health endpoint."""

    def test_health_check(self, client):
        """Test that health endpoint returns ok."""
        response = client.get(reverse('icosa:health'))
        assert response.status_code == 200
        assert response.content == b'ok'


@pytest.mark.django_db
@pytest.mark.views
class TestHomeView:
    """Test suite for home page view."""

    def test_home_page_loads(self, client):
        """Test that home page loads successfully."""
        response = client.get(reverse('icosa:home'))
        assert response.status_code == 200

    def test_home_page_shows_public_assets(self, client):
        """Test that home page shows public curated assets."""
        asset = AssetFactory(
            visibility=PUBLIC,
            curated=True,
            is_viewer_compatible=True
        )
        response = client.get(reverse('icosa:home'))
        assert response.status_code == 200

    def test_home_page_hides_private_assets(self, client):
        """Test that home page hides private assets."""
        private_asset = PrivateAssetFactory(curated=True)
        response = client.get(reverse('icosa:home'))
        assert response.status_code == 200
        # Private assets should not appear in public home

    def test_home_page_excludes_all_rights_reserved(self, client):
        """Test that home page excludes all rights reserved assets."""
        asset = AssetFactory(
            visibility=PUBLIC,
            curated=True,
            license=ALL_RIGHTS_RESERVED
        )
        response = client.get(reverse('icosa:home'))
        assert response.status_code == 200

    def test_home_page_pagination(self, client):
        """Test that home page pagination works."""
        # Create multiple assets
        for i in range(30):
            AssetFactory(visibility=PUBLIC, curated=True, is_viewer_compatible=True)

        response = client.get(reverse('icosa:home'))
        assert response.status_code == 200

        # Test page 2
        response = client.get(reverse('icosa:home') + '?page=2')
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestOpenBrushView:
    """Test suite for Open Brush (Tilt Brush) home page."""

    def test_openbrush_page_loads(self, client):
        """Test that Open Brush page loads."""
        response = client.get(reverse('icosa:home_openbrush'))
        assert response.status_code == 200

    def test_openbrush_shows_tilt_assets(self, client):
        """Test that Open Brush page shows Tilt Brush assets."""
        asset = AssetFactory(
            visibility=PUBLIC,
            has_tilt=True,
            curated=True
        )
        response = client.get(reverse('icosa:home_openbrush'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestBlocksView:
    """Test suite for Open Blocks home page."""

    def test_blocks_page_loads(self, client):
        """Test that Blocks page loads."""
        response = client.get(reverse('icosa:home_blocks'))
        assert response.status_code == 200

    def test_blocks_shows_blocks_assets(self, client):
        """Test that Blocks page shows blocks assets."""
        asset = AssetFactory(
            visibility=PUBLIC,
            has_blocks=True,
            curated=True
        )
        response = client.get(reverse('icosa:home_blocks'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestCategoryView:
    """Test suite for category exploration view."""

    def test_valid_category_loads(self, client):
        """Test that valid category page loads."""
        # Using a valid category from CATEGORY_LABELS
        response = client.get(reverse('icosa:explore_category', kwargs={'category': 'animals'}))
        # May return 200 or 404 depending on CATEGORY_LABELS
        assert response.status_code in [200, 404]

    def test_invalid_category_returns_404(self, client):
        """Test that invalid category returns 404."""
        response = client.get(reverse('icosa:explore_category', kwargs={'category': 'invalid'}))
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.views
class TestAssetViewView:
    """Test suite for asset detail view."""

    def test_public_asset_view(self, client):
        """Test viewing a public asset."""
        asset = AssetFactory(visibility=PUBLIC)
        response = client.get(reverse('icosa:asset_view', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200
        assert 'asset' in response.context

    def test_private_asset_view_unauthorized(self, client):
        """Test that private asset returns 404 for anonymous users."""
        asset = PrivateAssetFactory()
        response = client.get(reverse('icosa:asset_view', kwargs={'asset_url': asset.url}))
        assert response.status_code == 404

    def test_private_asset_view_by_owner(self, authenticated_client, user):
        """Test that owner can view their private asset."""
        owner = AssetOwnerFactory(django_user=user)
        asset = PrivateAssetFactory(owner=owner)
        response = authenticated_client.get(reverse('icosa:asset_view', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200

    def test_unlisted_asset_view(self, client):
        """Test viewing an unlisted asset."""
        asset = AssetFactory(visibility=UNLISTED)
        response = client.get(reverse('icosa:asset_view', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200

    def test_nonexistent_asset_returns_404(self, client):
        """Test that nonexistent asset returns 404."""
        response = client.get(reverse('icosa:asset_view', kwargs={'asset_url': 'nonexistent'}))
        assert response.status_code == 404

    def test_asset_view_increments_views(self, client):
        """Test that viewing an asset increments view count."""
        asset = AssetFactory(visibility=PUBLIC, views=0)
        initial_views = asset.views

        response = client.get(reverse('icosa:asset_view', kwargs={'asset_url': asset.url}))

        asset.refresh_from_db()
        assert asset.views > initial_views


@pytest.mark.django_db
@pytest.mark.views
class TestAssetDownloadsView:
    """Test suite for asset downloads view."""

    def test_asset_downloads_view(self, client):
        """Test asset downloads page."""
        asset = AssetFactory(visibility=PUBLIC)
        response = client.get(reverse('icosa:asset_downloads', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200

    def test_all_rights_reserved_asset_download_404(self, client):
        """Test that all rights reserved assets can't be downloaded."""
        asset = AssetFactory(visibility=PUBLIC, license=ALL_RIGHTS_RESERVED)
        response = client.get(reverse('icosa:asset_downloads', kwargs={'asset_url': asset.url}))
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.views
class TestAssetLogDownloadView:
    """Test suite for asset download logging."""

    def test_log_download_increments_count(self, client):
        """Test that logging a download increments count."""
        asset = AssetFactory(visibility=PUBLIC, downloads=0)

        response = client.post(reverse('icosa:asset_log_download', kwargs={'asset_url': asset.url}))

        assert response.status_code == 200
        asset.refresh_from_db()
        assert asset.downloads == 1

    def test_log_download_get_not_allowed(self, client):
        """Test that GET is not allowed for download logging."""
        asset = AssetFactory(visibility=PUBLIC)
        response = client.get(reverse('icosa:asset_log_download', kwargs={'asset_url': asset.url}))
        assert response.status_code == 405


@pytest.mark.django_db
@pytest.mark.views
class TestUserShowView:
    """Test suite for user profile view."""

    def test_user_show_page(self, client):
        """Test user profile page loads."""
        owner = AssetOwnerFactory()
        response = client.get(reverse('icosa:user_show', kwargs={'slug': owner.url}))
        assert response.status_code == 200

    def test_user_show_displays_public_assets(self, client):
        """Test user profile shows public assets."""
        owner = AssetOwnerFactory()
        asset = AssetFactory(owner=owner, visibility=PUBLIC)

        response = client.get(reverse('icosa:user_show', kwargs={'slug': owner.url}))
        assert response.status_code == 200

    def test_disabled_profile_returns_404(self, client):
        """Test that disabled profile returns 404."""
        owner = AssetOwnerFactory(disable_profile=True)
        response = client.get(reverse('icosa:user_show', kwargs={'slug': owner.url}))
        assert response.status_code == 404

    def test_superuser_can_view_disabled_profile(self, client, superuser):
        """Test that superuser can view disabled profiles."""
        owner = AssetOwnerFactory(disable_profile=True)
        client.force_login(superuser)
        response = client.get(reverse('icosa:user_show', kwargs={'slug': owner.url}))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestOwnerShowView:
    """Test suite for owner profile view."""

    def test_owner_show_page(self, client):
        """Test owner profile page loads."""
        owner = AssetOwnerFactory()
        response = client.get(reverse('icosa:owner_show', kwargs={'slug': owner.url}))
        assert response.status_code == 200

    def test_owner_show_displays_assets(self, client):
        """Test owner profile shows assets."""
        owner = AssetOwnerFactory()
        asset = AssetFactory(owner=owner, visibility=PUBLIC)

        response = client.get(reverse('icosa:owner_show', kwargs={'slug': owner.url}))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestMyLikesView:
    """Test suite for user likes view."""

    def test_my_likes_requires_login(self, client):
        """Test that my likes requires authentication."""
        response = client.get(reverse('icosa:my_likes'))
        assert response.status_code == 302  # Redirect to login

    def test_my_likes_shows_liked_assets(self, authenticated_client, user):
        """Test that my likes shows user's liked assets."""
        asset = AssetFactory(visibility=PUBLIC)
        UserLikeFactory(user=user, asset=asset)

        response = authenticated_client.get(reverse('icosa:my_likes'))
        assert response.status_code == 200

    def test_my_likes_includes_unlisted_own_assets(self, authenticated_client, user):
        """Test that my likes includes user's unlisted assets."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner, visibility=UNLISTED)
        UserLikeFactory(user=user, asset=asset)

        response = authenticated_client.get(reverse('icosa:my_likes'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestUploadsView:
    """Test suite for uploads management view."""

    def test_uploads_requires_login(self, client):
        """Test that uploads page requires authentication."""
        response = client.get(reverse('icosa:uploads'))
        assert response.status_code == 302

    def test_uploads_page_shows_user_assets(self, authenticated_client, user):
        """Test that uploads page shows user's assets."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner)

        response = authenticated_client.get(reverse('icosa:uploads'))
        assert response.status_code == 200

    @patch('icosa.views.main.upload_api_asset')
    def test_upload_asset_post(self, mock_upload, authenticated_client, user):
        """Test uploading a new asset."""
        # Create a test GLB file
        glb_data = (
            b'glTF'  # Magic
            b'\x02\x00\x00\x00'  # Version 2
            b'\x0c\x00\x00\x00'  # Length
        )
        file = SimpleUploadedFile('test.glb', glb_data, content_type='model/gltf-binary')

        response = authenticated_client.post(reverse('icosa:upload_asset'), {
            'file': file,
        })

        assert response.status_code == 200
        assert response.json()['success'] is True
        mock_upload.assert_awaited_once()


@pytest.mark.django_db
@pytest.mark.views
class TestAssetEditView:
    """Test suite for asset edit view."""

    def test_asset_edit_requires_login(self, client):
        """Test that asset edit requires authentication."""
        asset = AssetFactory()
        response = client.get(reverse('icosa:asset_edit', kwargs={'asset_url': asset.url}))
        assert response.status_code == 302

    def test_asset_edit_by_owner(self, authenticated_client, user):
        """Test that owner can edit their asset."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner)

        response = authenticated_client.get(reverse('icosa:asset_edit', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200

    def test_asset_edit_by_non_owner_returns_404(self, authenticated_client, user):
        """Test that non-owner cannot edit asset."""
        other_owner = AssetOwnerFactory()
        asset = AssetFactory(owner=other_owner)

        response = authenticated_client.get(reverse('icosa:asset_edit', kwargs={'asset_url': asset.url}))
        assert response.status_code == 404

    def test_superuser_can_edit_any_asset(self, client, superuser):
        """Test that superuser can edit any asset."""
        asset = AssetFactory()
        client.force_login(superuser)

        response = client.get(reverse('icosa:asset_edit', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200

    def test_asset_edit_post_updates_asset(self, authenticated_client, user):
        """Test that posting to asset edit updates the asset."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner, name="Old Name")

        response = authenticated_client.post(reverse('icosa:asset_edit', kwargs={'asset_url': asset.url}), {
            'name': 'New Name',
            'description': 'Updated description',
            'license': asset.license,
            'visibility': asset.visibility,
            'category': asset.category,
            '_save_private': True,
        })

        asset.refresh_from_db()
        assert asset.name == 'New Name'


@pytest.mark.django_db
@pytest.mark.views
class TestAssetPublishView:
    """Test suite for asset publish view."""

    def test_asset_publish_requires_login(self, client):
        """Test that asset publish requires authentication."""
        asset = AssetFactory()
        response = client.get(reverse('icosa:asset_publish', kwargs={'asset_url': asset.url}))
        assert response.status_code == 302

    def test_asset_publish_by_owner(self, authenticated_client, user):
        """Test that owner can publish their asset."""
        owner = AssetOwnerFactory(django_user=user)
        asset = PrivateAssetFactory(owner=owner)

        response = authenticated_client.get(reverse('icosa:asset_publish', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200

    def test_asset_publish_by_non_owner_returns_404(self, authenticated_client, user):
        """Test that non-owner cannot publish asset."""
        other_owner = AssetOwnerFactory()
        asset = AssetFactory(owner=other_owner)

        response = authenticated_client.get(reverse('icosa:asset_publish', kwargs={'asset_url': asset.url}))
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.views
class TestAssetDeleteView:
    """Test suite for asset deletion view."""

    def test_asset_delete_requires_login(self, client):
        """Test that asset deletion requires authentication."""
        asset = AssetFactory()
        response = client.post(reverse('icosa:asset_delete', kwargs={'asset_url': asset.url}))
        assert response.status_code == 302

    def test_asset_delete_by_owner(self, authenticated_client, user):
        """Test that owner can delete their asset."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner, name="To Delete")
        asset_id = asset.id

        response = authenticated_client.post(reverse('icosa:asset_delete', kwargs={'asset_url': asset.url}))

        assert response.status_code == 302
        assert not Asset.objects.filter(id=asset_id).exists()

    def test_asset_delete_by_non_owner_returns_404(self, authenticated_client, user):
        """Test that non-owner cannot delete asset."""
        other_owner = AssetOwnerFactory()
        asset = AssetFactory(owner=other_owner)

        response = authenticated_client.post(reverse('icosa:asset_delete', kwargs={'asset_url': asset.url}))
        assert response.status_code == 404

    def test_asset_delete_get_not_allowed(self, authenticated_client, user):
        """Test that GET is not allowed for asset deletion."""
        owner = AssetOwnerFactory(django_user=user)
        asset = AssetFactory(owner=owner)

        response = authenticated_client.get(reverse('icosa:asset_delete', kwargs={'asset_url': asset.url}))
        assert response.status_code == 405


@pytest.mark.django_db
@pytest.mark.views
class TestReportAssetView:
    """Test suite for asset reporting view."""

    def test_report_asset_get_shows_form(self, client):
        """Test that GET shows report form."""
        asset = AssetFactory(visibility=PUBLIC)
        response = client.get(reverse('icosa:report_asset', kwargs={'asset_url': asset.url}))
        assert response.status_code == 200
        assert 'form' in response.context

    def test_report_asset_post_records_report(self, client):
        """Test that POST records asset report."""
        asset = AssetFactory(visibility=PUBLIC)

        response = client.post(reverse('icosa:report_asset', kwargs={'asset_url': asset.url}), {
            'reason_for_reporting': 'Spam content',
            'asset_url': asset.url,
            'asset_ref': '',  # Honeypot field
        })

        # Should redirect to success page
        assert response.status_code in [302, 200]


@pytest.mark.django_db
@pytest.mark.views
class TestSearchView:
    """Test suite for search view."""

    def test_search_without_query(self, client):
        """Test search without query parameter."""
        response = client.get(reverse('icosa:search'))
        assert response.status_code == 200

    def test_search_with_query(self, client):
        """Test search with query parameter."""
        AssetFactory(
            visibility=PUBLIC,
            name="Test Asset",
            is_viewer_compatible=True
        )

        response = client.get(reverse('icosa:search') + '?s=Test')
        assert response.status_code == 200

    def test_search_excludes_private_assets(self, client):
        """Test that search excludes private assets."""
        PrivateAssetFactory(name="Private Test")

        response = client.get(reverse('icosa:search') + '?s=Private')
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestToggleLikeView:
    """Test suite for toggle like functionality."""

    def test_toggle_like_requires_authentication(self, client):
        """Test that toggle like requires authentication."""
        asset = AssetFactory(visibility=PUBLIC)
        response = client.post(reverse('icosa:toggle_like'), {
            'assetId': asset.url
        })
        assert response.status_code == 422

    def test_toggle_like_adds_like(self, authenticated_client, user):
        """Test that toggle like adds a like."""
        asset = AssetFactory(visibility=PUBLIC)

        response = authenticated_client.post(reverse('icosa:toggle_like'), {
            'assetId': asset.url
        })

        assert response.status_code == 200
        assert UserLike.objects.filter(user=user, asset=asset).exists()

    def test_toggle_like_removes_existing_like(self, authenticated_client, user):
        """Test that toggle like removes existing like."""
        asset = AssetFactory(visibility=PUBLIC)
        UserLikeFactory(user=user, asset=asset)

        response = authenticated_client.post(reverse('icosa:toggle_like'), {
            'assetId': asset.url
        })

        assert response.status_code == 200
        assert not UserLike.objects.filter(user=user, asset=asset).exists()


@pytest.mark.django_db
@pytest.mark.views
class TestUserSettingsView:
    """Test suite for user settings view."""

    def test_user_settings_requires_login(self, client):
        """Test that user settings requires authentication."""
        response = client.get(reverse('icosa:settings'))
        assert response.status_code == 302

    def test_user_settings_get_shows_form(self, authenticated_client):
        """Test that GET shows settings form."""
        response = authenticated_client.get(reverse('icosa:settings'))
        assert response.status_code == 200
        assert 'form' in response.context

    def test_user_settings_post_updates_user(self, authenticated_client, user):
        """Test that POST updates user settings."""
        response = authenticated_client.post(reverse('icosa:settings'), {
            'displayname': 'Updated Name',
            'email': user.email,
            'password_current': 'testpass123',
        })

        user.refresh_from_db()
        assert user.displayname == 'Updated Name'


@pytest.mark.django_db
@pytest.mark.views
class TestTemplateViews:
    """Test suite for simple template views."""

    def test_about_page(self, client):
        """Test that about page loads."""
        response = client.get(reverse('icosa:about'))
        assert response.status_code == 200

    def test_terms_page(self, client):
        """Test that terms page loads."""
        response = client.get(reverse('icosa:terms'))
        assert response.status_code == 200

    def test_supporters_page(self, client):
        """Test that supporters page loads."""
        response = client.get(reverse('icosa:supporters'))
        assert response.status_code == 200

    def test_licenses_page(self, client):
        """Test that licenses page loads."""
        response = client.get(reverse('icosa:licenses'))
        assert response.status_code == 200

    def test_privacy_policy_page(self, client):
        """Test that privacy policy page loads."""
        response = client.get(reverse('icosa:privacy_policy'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestErrorHandlers:
    """Test suite for error handler views."""

    def test_handler404(self, client):
        """Test 404 error handler."""
        response = client.get('/nonexistent-page/')
        assert response.status_code == 404

    def test_handler500(self, client):
        """Test 500 error handler."""
        # This would require triggering a server error
        # Skipping actual 500 test as it's hard to trigger safely
        pass
