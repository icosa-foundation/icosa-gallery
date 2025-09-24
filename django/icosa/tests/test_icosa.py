import pytest
from django.contrib.auth import get_user_model
from icosa.models import Asset, AssetOwner, Tag

User = get_user_model()


@pytest.mark.django_db()
class TestAssetDenorm:
    def test_immediate_save(self, asset_fixture: Asset):
        # Fake saving an asset immediately after creation. Simulates a
        # situation where a comparison between create_time and update_time
        # results in a divide-by-zero error.
        asset_fixture.update_time = asset_fixture.create_time
        asset_fixture.save()
        # Dummy assertion just so the test does something to pass. The failure
        # state for this test is raising.
        assert True

    def test_rank(self, asset_fixture: Asset):
        asset_fixture.save()
        # This seems to be the default rank. I'm not particularly fussed what
        # this is, but a departure from this value means something changed
        # which we didn't expect.
        assert asset_fixture.rank == 10100.0

    def test_search_text(self, asset_fixture: Asset):
        asset_fixture.save()
        assert asset_fixture.search_text == "Test Asset A Test Asset dog fish test1"


@pytest.fixture
def user_fixture():
    return User.objects.create(
        username="mail@example.com",
        email="mail@example.com",
        displayname="test1",
    )


@pytest.fixture
def assetowner_fixture(user_fixture: User):
    return AssetOwner.objects.create(
        url="abcdef01",
        email="mail@example.com",
        displayname="test1",
        description="Test owner 1",
        django_user=user_fixture,
    )


@pytest.fixture
def tag_dog_fixture():
    return Tag.objects.create(name="dog")


@pytest.fixture
def tag_fish_fixture():
    return Tag.objects.create(name="fish")


@pytest.fixture
def asset_fixture(assetowner_fixture: AssetOwner, tag_dog_fixture: Tag, tag_fish_fixture: Tag):
    asset = Asset.objects.create(
        url="Url123abcXX",
        name="Test Asset",
        owner=assetowner_fixture,
        description="A Test Asset",
        visibility="Public",
    )
    asset_tags = [tag_dog_fixture, tag_fish_fixture]
    asset.tags.set(asset_tags)
    return asset
