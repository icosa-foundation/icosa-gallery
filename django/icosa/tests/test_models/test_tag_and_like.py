"""
Tests for Tag and UserLike models.
"""
import pytest
from datetime import timedelta
from django.utils import timezone

from icosa.models import Tag, UserLike
from icosa.tests.fixtures.factories import (
    TagFactory,
    UserLikeFactory,
    AssetFactory,
    UserFactory,
)


@pytest.mark.django_db
@pytest.mark.models
class TestTagModel:
    """Test suite for Tag model."""

    def test_create_tag(self):
        """Test creating a tag."""
        tag = TagFactory()
        assert tag.id is not None
        assert tag.name is not None

    def test_tag_string_representation(self):
        """Test string representation of tag."""
        tag = TagFactory(name='test-tag')
        assert str(tag) == 'test-tag'

    def test_tag_name_unique(self):
        """Test that tag name must be unique."""
        name = 'unique-tag'
        TagFactory(name=name)

        with pytest.raises(Exception):
            TagFactory(name=name)

    def test_tag_name_max_length(self):
        """Test tag name has max length of 255."""
        tag = TagFactory(name='a' * 255)
        assert len(tag.name) == 255

    def test_tag_ordering(self):
        """Test tags are ordered by name."""
        tag_c = TagFactory(name='charlie')
        tag_a = TagFactory(name='alpha')
        tag_b = TagFactory(name='bravo')

        tags = Tag.objects.all()
        assert tags[0] == tag_a
        assert tags[1] == tag_b
        assert tags[2] == tag_c

    def test_tag_can_be_applied_to_assets(self):
        """Test tags can be applied to multiple assets."""
        tag = TagFactory(name='3d-model')
        asset1 = AssetFactory()
        asset2 = AssetFactory()

        asset1.tags.add(tag)
        asset2.tags.add(tag)

        assert tag in asset1.tags.all()
        assert tag in asset2.tags.all()

    def test_asset_can_have_multiple_tags(self):
        """Test asset can have multiple tags."""
        asset = AssetFactory()
        tag1 = TagFactory(name='character')
        tag2 = TagFactory(name='animated')
        tag3 = TagFactory(name='low-poly')

        asset.tags.add(tag1, tag2, tag3)

        assert asset.tags.count() == 3
        assert tag1 in asset.tags.all()
        assert tag2 in asset.tags.all()
        assert tag3 in asset.tags.all()

    def test_deleting_tag_removes_from_assets(self):
        """Test deleting tag removes it from assets."""
        tag = TagFactory(name='test-tag')
        asset = AssetFactory()
        asset.tags.add(tag)

        assert tag in asset.tags.all()

        tag.delete()
        asset.refresh_from_db()

        assert tag not in asset.tags.all()

    def test_tag_case_sensitive(self):
        """Test that tag names are case sensitive."""
        TagFactory(name='Test')
        # Should be able to create tag with different case
        tag_lower = TagFactory(name='test')
        assert tag_lower.name == 'test'


@pytest.mark.django_db
@pytest.mark.models
class TestUserLikeModel:
    """Test suite for UserLike model."""

    def test_create_user_like(self):
        """Test creating a user like."""
        like = UserLikeFactory()
        assert like.id is not None
        assert like.user is not None
        assert like.asset is not None
        assert like.date_liked is not None

    def test_user_like_string_representation(self):
        """Test string representation of user like."""
        user = UserFactory(displayname='Test User')
        asset = AssetFactory(name='Test Asset')
        like = UserLikeFactory(user=user, asset=asset)

        str_repr = str(like)
        assert 'Test User' in str_repr
        assert 'Test Asset' in str_repr
        assert '->' in str_repr
        assert '@' in str_repr

    def test_date_liked_auto_now_add(self):
        """Test date_liked is automatically set on creation."""
        like = UserLikeFactory()
        assert like.date_liked is not None
        # Should be recent (within last minute)
        now = timezone.now()
        assert (now - like.date_liked).total_seconds() < 60

    def test_user_relationship(self):
        """Test relationship with user."""
        user = UserFactory()
        asset = AssetFactory()
        like = UserLikeFactory(user=user, asset=asset)

        assert like.user == user
        assert like in user.likedassets.all()

    def test_asset_relationship(self):
        """Test relationship with asset."""
        asset = AssetFactory()
        user = UserFactory()
        like = UserLikeFactory(user=user, asset=asset)

        assert like.asset == asset
        assert like in asset.userlike_set.all()

    def test_user_can_like_multiple_assets(self):
        """Test user can like multiple assets."""
        user = UserFactory()
        asset1 = AssetFactory()
        asset2 = AssetFactory()
        asset3 = AssetFactory()

        like1 = UserLikeFactory(user=user, asset=asset1)
        like2 = UserLikeFactory(user=user, asset=asset2)
        like3 = UserLikeFactory(user=user, asset=asset3)

        user_likes = user.likedassets.all()
        assert like1 in user_likes
        assert like2 in user_likes
        assert like3 in user_likes
        assert user_likes.count() == 3

    def test_asset_can_be_liked_by_multiple_users(self):
        """Test asset can be liked by multiple users."""
        asset = AssetFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        like1 = UserLikeFactory(user=user1, asset=asset)
        like2 = UserLikeFactory(user=user2, asset=asset)
        like3 = UserLikeFactory(user=user3, asset=asset)

        asset_likes = asset.userlike_set.all()
        assert like1 in asset_likes
        assert like2 in asset_likes
        assert like3 in asset_likes
        assert asset_likes.count() == 3

    def test_deleting_user_deletes_likes(self):
        """Test deleting user cascades to delete their likes."""
        user = UserFactory()
        asset = AssetFactory()
        like = UserLikeFactory(user=user, asset=asset)

        like_id = like.id
        user.delete()

        # Like should be deleted
        assert not UserLike.objects.filter(id=like_id).exists()

    def test_deleting_asset_deletes_likes(self):
        """Test deleting asset cascades to delete its likes."""
        user = UserFactory()
        asset = AssetFactory()
        like = UserLikeFactory(user=user, asset=asset)

        like_id = like.id
        asset.delete()

        # Like should be deleted
        assert not UserLike.objects.filter(id=like_id).exists()

    def test_like_chronological_ordering(self):
        """Test likes can be ordered by date_liked."""
        asset = AssetFactory()
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        # Create likes at different times
        like1 = UserLikeFactory(user=user1, asset=asset)
        like2 = UserLikeFactory(user=user2, asset=asset)
        like3 = UserLikeFactory(user=user3, asset=asset)

        now = timezone.now()
        UserLike.objects.filter(pk=like1.pk).update(date_liked=now - timedelta(seconds=2))
        UserLike.objects.filter(pk=like2.pk).update(date_liked=now - timedelta(seconds=1))
        UserLike.objects.filter(pk=like3.pk).update(date_liked=now)

        # Get likes ordered by date
        likes_desc = asset.userlike_set.order_by('-date_liked')
        likes_asc = asset.userlike_set.order_by('date_liked')

        # Most recent should be first in descending order
        assert likes_desc.first() == like3
        # Oldest should be first in ascending order
        assert likes_asc.first() == like1

    def test_user_can_unlike_asset(self):
        """Test user can remove their like."""
        user = UserFactory()
        asset = AssetFactory()
        like = UserLikeFactory(user=user, asset=asset)

        assert like in asset.userlike_set.all()

        like.delete()

        assert like not in asset.userlike_set.all()
        assert asset.userlike_set.count() == 0

    def test_duplicate_like_not_prevented_at_model_level(self):
        """Test that duplicate likes are not prevented at model level.

        Note: Application logic should prevent duplicates, but the model
        itself doesn't enforce uniqueness.
        """
        user = UserFactory()
        asset = AssetFactory()

        like1 = UserLikeFactory(user=user, asset=asset)
        like2 = UserLikeFactory(user=user, asset=asset)

        # Both likes should exist
        assert UserLike.objects.filter(user=user, asset=asset).count() == 2

    def test_get_asset_like_count(self):
        """Test getting total like count for an asset."""
        asset = AssetFactory()

        # Create 5 likes
        for _ in range(5):
            user = UserFactory()
            UserLikeFactory(user=user, asset=asset)

        like_count = asset.userlike_set.count()
        assert like_count == 5

    def test_get_user_liked_assets(self):
        """Test getting all assets liked by a user."""
        user = UserFactory()

        # Create assets and like them
        assets = [AssetFactory() for _ in range(3)]
        for asset in assets:
            UserLikeFactory(user=user, asset=asset)

        # Get all liked assets
        liked_asset_ids = user.likedassets.values_list('asset_id', flat=True)

        for asset in assets:
            assert asset.id in liked_asset_ids
