import pytest
from django.contrib.auth import get_user_model
from icosa.models import Asset, AssetOwner

User = get_user_model()


@pytest.mark.django_db()
class TestThing:
    def test_frobnicate(self, asset_fixture: Asset):
        assert asset_fixture.url == "Url123abcX"


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
def asset_fixture(assetowner_fixture: AssetOwner):
    return Asset.objects.create(
        url="Url123abcXX",
        name="Test Asset",
        owner=assetowner_fixture,
        description="A Test Asset",
        visibility="Public",
    )
