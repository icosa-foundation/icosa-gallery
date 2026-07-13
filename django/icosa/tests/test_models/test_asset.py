"""
Tests for the Asset model.
"""
import pytest
from asgiref.sync import async_to_sync
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from icosa.models import Asset, Format, Resource, Tag
from icosa.models.common import PUBLIC, PRIVATE, UNLISTED, ALL_RIGHTS_RESERVED
from icosa.tests.fixtures.factories import (
    AssetFactory,
    AssetOwnerFactory,
    UserFactory,
    TagFactory,
    FormatFactory,
    GLBFormatFactory,
    OBJFormatFactory,
    ResourceFactory,
    UserLikeFactory,
    PrivateAssetFactory,
    UnlistedAssetFactory,
    create_asset_with_formats,
)


@pytest.mark.django_db
@pytest.mark.models
class TestAssetModel:
    """Test suite for Asset model."""

    def test_create_asset(self):
        """Test creating an asset with all required fields."""
        asset = AssetFactory()
        assert asset.id is not None
        assert asset.name is not None
        assert asset.owner is not None
        assert asset.create_time is not None

    def test_asset_string_representation(self):
        """Test the string representation of asset."""
        asset = AssetFactory(name='Test Asset')
        assert str(asset) == 'Test Asset'

    def test_asset_string_representation_unnamed(self):
        """Test string representation for unnamed asset."""
        asset = AssetFactory(name=None)
        assert str(asset) == '(Un-named asset)'

    def test_asset_url_unique(self):
        """Test that asset url must be unique."""
        url = 'unique-asset-url'
        AssetFactory(url=url)

        with pytest.raises(Exception):
            AssetFactory(url=url)

    def test_is_published_public(self):
        """Test is_published returns True for public assets."""
        asset = AssetFactory(visibility=PUBLIC)
        assert asset.is_published is True

    def test_is_published_unlisted(self):
        """Test is_published returns True for unlisted assets."""
        asset = AssetFactory(visibility=UNLISTED)
        assert asset.is_published is True

    def test_is_published_private(self):
        """Test is_published returns False for private assets."""
        asset = AssetFactory(visibility=PRIVATE)
        assert asset.is_published is False

    def test_slug_property(self):
        """Test slug property generates correct slug from name."""
        asset = AssetFactory(name='Test Asset Name')
        assert asset.slug == 'test-asset-name'

    def test_timestamp_property(self):
        """Test timestamp property extracts timestamp from snowflake ID."""
        asset = AssetFactory()
        timestamp = asset.timestamp
        assert isinstance(timestamp, datetime)
        assert timestamp.year >= 2021

    def test_get_base_license_all_rights_reserved(self):
        """Test get_base_license for all rights reserved."""
        asset = AssetFactory(license='ALL_RIGHTS_RESERVED')
        assert asset.get_base_license() == 'ALL_RIGHTS_RESERVED'

    def test_get_base_license_cc0(self):
        """Test get_base_license for CC0."""
        asset = AssetFactory(license='CREATIVE_COMMONS_0')
        assert asset.get_base_license() == 'CC0'

    def test_get_base_license_v3(self):
        """Test get_base_license for v3 CC licenses."""
        asset = AssetFactory(license='CREATIVE_COMMONS_BY_3_0')
        assert asset.get_base_license() == 'CREATIVE_COMMONS_BY'

    def test_get_base_license_v4(self):
        """Test get_base_license for v4 CC licenses."""
        asset = AssetFactory(license='CREATIVE_COMMONS_BY_4_0')
        assert asset.get_base_license() == 'CREATIVE_COMMONS_BY'

    def test_get_license_version_all_rights_reserved(self):
        """Test get_license_version for all rights reserved."""
        asset = AssetFactory(license='ALL_RIGHTS_RESERVED')
        assert asset.get_license_version() is None

    def test_get_license_version_v3(self):
        """Test get_license_version for v3 licenses."""
        asset = AssetFactory(license='CREATIVE_COMMONS_BY_3_0')
        assert asset.get_license_version() == '3.0'

    def test_get_license_version_v4(self):
        """Test get_license_version for v4 licenses."""
        asset = AssetFactory(license='CREATIVE_COMMONS_BY_4_0')
        assert asset.get_license_version() == '4.0'

    def test_get_absolute_url(self):
        """Test get_absolute_url returns correct URL."""
        asset = AssetFactory(url='test-asset')
        url = asset.get_absolute_url()
        expected = reverse("icosa:asset_view", kwargs={"asset_url": 'test-asset'})
        assert url == expected

    def test_get_edit_url(self):
        """Test get_edit_url returns correct URL."""
        asset = AssetFactory(url='test-asset')
        url = asset.get_edit_url()
        expected = reverse("icosa:asset_edit", kwargs={"asset_url": 'test-asset'})
        assert url == expected

    def test_get_delete_url(self):
        """Test get_delete_url returns correct URL."""
        asset = AssetFactory(url='test-asset')
        url = asset.get_delete_url()
        expected = reverse("icosa:asset_delete", kwargs={"asset_url": 'test-asset'})
        assert url == expected

    def test_is_owned_by_django_user_true(self):
        """Test is_owned_by_django_user returns True for owner."""
        owner = AssetOwnerFactory()
        asset = AssetFactory(owner=owner)
        user = owner.django_user
        assert asset.is_owned_by_django_user(user) is True

    def test_is_owned_by_django_user_false(self):
        """Test is_owned_by_django_user returns False for non-owner."""
        asset = AssetFactory()
        other_user = UserFactory()
        assert asset.is_owned_by_django_user(other_user) is False

    def test_is_owned_by_django_user_anonymous(self):
        """Test is_owned_by_django_user returns False for anonymous user."""
        asset = AssetFactory()
        assert asset.is_owned_by_django_user(None) is False

    def test_update_search_text(self):
        """Test update_search_text updates search_text field."""
        owner = AssetOwnerFactory(displayname='Test Owner')
        asset = AssetFactory(
            owner=owner,
            name='Test Asset',
            description='Test description'
        )
        tag1 = TagFactory(name='tag1')
        tag2 = TagFactory(name='tag2')
        asset.tags.add(tag1, tag2)

        asset.update_search_text()

        assert 'Test Asset' in asset.search_text
        assert 'Test description' in asset.search_text
        assert 'tag1' in asset.search_text
        assert 'tag2' in asset.search_text
        assert 'Test Owner' in asset.search_text

    def test_denorm_format_types(self):
        """Test denorm_format_types updates format boolean fields."""
        asset, formats = create_asset_with_formats(num_formats=2)

        asset.denorm_format_types()

        # Check that has_* fields are updated based on formats
        assert asset.has_gltf2 is True or asset.has_obj is True

    def test_get_updated_rank(self):
        """Test get_updated_rank calculates rank correctly."""
        asset = AssetFactory(likes=10, views=100)
        rank = asset.get_updated_rank()

        assert rank > 0
        assert isinstance(rank, float)

    def test_inc_views_and_rank(self):
        """Test inc_views_and_rank increments views and updates rank."""
        asset = AssetFactory(views=5)
        initial_views = asset.views

        asset.inc_views_and_rank()

        assert asset.views == initial_views + 1
        assert asset.rank > 0

    def test_denorm_liked_time(self):
        """Test denorm_liked_time updates last_liked_time."""
        asset = AssetFactory()
        user = UserFactory()

        # Create a like
        like = UserLikeFactory(user=user, asset=asset)

        asset.denorm_liked_time()

        assert asset.last_liked_time is not None
        assert asset.last_liked_time == like.date_liked

    def test_get_preferred_viewer_format_glb(self):
        """Test get_preferred_viewer_format_for_assignment prefers GLB."""
        asset = AssetFactory()
        glb_format = GLBFormatFactory(asset=asset)
        obj_format = OBJFormatFactory(asset=asset)

        # Create root resources
        ResourceFactory(asset=asset, format=None)
        glb_format.root_resource = ResourceFactory(asset=asset, format=glb_format)
        glb_format.save()
        obj_format.root_resource = ResourceFactory(asset=asset, format=obj_format)
        obj_format.save()

        preferred = async_to_sync(asset.get_preferred_viewer_format_for_assignment)()

        assert preferred == glb_format

    def test_assign_preferred_viewer_format(self):
        """Test assign_preferred_viewer_format sets the preferred format."""
        asset = AssetFactory()
        glb_format = GLBFormatFactory(asset=asset)
        glb_format.root_resource = ResourceFactory(asset=asset, format=glb_format)
        glb_format.save()

        result = async_to_sync(asset.assign_preferred_viewer_format)()

        assert result == glb_format
        glb_format.refresh_from_db()
        assert glb_format.is_preferred_for_gallery_viewer is True

    def test_preferred_viewer_format_property(self):
        """Test preferred_viewer_format property returns correct format."""
        asset = AssetFactory()
        glb_format = GLBFormatFactory(
            asset=asset,
            is_preferred_for_gallery_viewer=True
        )

        assert asset.preferred_viewer_format == glb_format

    def test_tags_relationship(self):
        """Test many-to-many relationship with tags."""
        asset = AssetFactory()
        tag1 = TagFactory(name='test-tag-1')
        tag2 = TagFactory(name='test-tag-2')

        asset.tags.add(tag1, tag2)

        assert asset.tags.count() == 2
        assert tag1 in asset.tags.all()
        assert tag2 in asset.tags.all()

    def test_asset_save_creates_timestamp(self):
        """Test that saving new asset creates create_time."""
        asset = AssetFactory()
        assert asset.create_time is not None

    def test_asset_visibility_choices(self):
        """Test asset can be created with different visibility choices."""
        public_asset = AssetFactory(visibility=PUBLIC)
        private_asset = PrivateAssetFactory(visibility=PRIVATE)
        unlisted_asset = UnlistedAssetFactory(visibility=UNLISTED)

        assert public_asset.visibility == PUBLIC
        assert private_asset.visibility == PRIVATE
        assert unlisted_asset.visibility == UNLISTED

    def test_asset_state_field(self):
        """Test asset state field."""
        asset = AssetFactory(state='PUBLISHED')
        assert asset.state == 'PUBLISHED'

    def test_triangle_count_field(self):
        """Test triangle_count field stores integer."""
        asset = AssetFactory()
        Asset.objects.filter(pk=asset.pk).update(triangle_count=5000)
        asset.refresh_from_db()
        assert asset.triangle_count == 5000
        assert isinstance(asset.triangle_count, int)

    def test_likes_views_downloads_counters(self):
        """Test likes, views, and downloads counters."""
        asset = AssetFactory(likes=10, views=100, downloads=5)
        assert asset.likes == 10
        assert asset.views == 100
        assert asset.downloads == 5

    def test_polyid_and_polydata_fields(self):
        """Test polyid and polydata fields for imported assets."""
        polydata = {'source': 'google_poly', 'data': 'test'}
        asset = AssetFactory(polyid='abc123', polydata=polydata)

        assert asset.polyid == 'abc123'
        assert asset.polydata == polydata

    def test_remix_ids_field(self):
        """Test remix_ids JSON field."""
        remix_ids = ['asset1', 'asset2', 'asset3']
        asset = AssetFactory(remix_ids=remix_ids)

        assert asset.remix_ids == remix_ids
        assert len(asset.remix_ids) == 3

    def test_category_field(self):
        """Test category field."""
        asset = AssetFactory(category='ANIMALS')
        assert asset.category == 'ANIMALS'

    def test_camera_and_transform_json_fields(self):
        """Test camera and transform JSON fields."""
        camera = {'position': [0, 0, 5], 'rotation': [0, 0, 0]}
        transform = {'scale': [1, 1, 1], 'position': [0, 0, 0]}

        asset = AssetFactory(camera=camera, transform=transform)

        assert asset.camera == camera
        assert asset.transform == transform

    def test_is_viewer_compatible_field(self):
        """Test is_viewer_compatible denormalized field."""
        asset = AssetFactory()
        Asset.objects.filter(pk=asset.pk).update(is_viewer_compatible=True)
        asset.refresh_from_db()
        assert asset.is_viewer_compatible is True

    def test_get_license_icons_cc_by(self):
        """Test get_license_icons for CC-BY license."""
        asset = AssetFactory(license='CREATIVE_COMMONS_BY_3_0')
        icons = asset.get_license_icons()

        assert 'cc.svg' in icons
        assert 'by.svg' in icons

    def test_get_license_icons_all_rights_reserved(self):
        """Test get_license_icons for all rights reserved."""
        asset = AssetFactory(license=ALL_RIGHTS_RESERVED)
        icons = asset.get_license_icons()

        assert '&copy;' in icons
