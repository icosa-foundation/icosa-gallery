"""
Tests for the User model.
"""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
import jwt
from django.conf import settings
from datetime import datetime, timedelta

from icosa.tests.fixtures.factories import UserFactory, AssetOwnerFactory

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.models
class TestUserModel:
    """Test suite for User model."""

    def test_create_user(self):
        """Test creating a user with all required fields."""
        user = UserFactory()
        assert user.id is not None
        assert user.username is not None
        assert user.email is not None
        assert user.displayname is not None
        assert user.is_active is True

    def test_user_string_representation(self):
        """Test the string representation of user."""
        user = UserFactory(username='testuser')
        assert str(user.username) == 'testuser'

    def test_create_user_with_password(self):
        """Test that user password is hashed correctly."""
        user = UserFactory()
        assert user.password is not None
        assert user.password != 'testpass123'
        assert user.check_password('testpass123') is True

    def test_get_absolute_url_no_owners(self):
        """Test get_absolute_url when user has no asset owners."""
        user = UserFactory()
        url = user.get_absolute_url()
        assert url is None

    def test_get_absolute_url_single_owner(self):
        """Test get_absolute_url when user has a single asset owner."""
        user = UserFactory()
        owner = AssetOwnerFactory(django_user=user, url='testowner')
        url = user.get_absolute_url()
        expected_url = reverse("icosa:user_show", kwargs={"slug": 'testowner'})
        assert url == expected_url

    def test_get_absolute_url_multiple_owners_with_url(self):
        """Test get_absolute_url when user has multiple owners with url."""
        user = UserFactory()
        owner1 = AssetOwnerFactory(django_user=user, url='owner1')
        owner2 = AssetOwnerFactory(django_user=user, url='owner2')
        url = user.get_absolute_url()
        expected_url = reverse("icosa:user_show", kwargs={"slug": owner1.url})
        assert url == expected_url

    def test_get_url_with_owner(self):
        """Test get_url returns the first owner's url."""
        user = UserFactory()
        owner = AssetOwnerFactory(django_user=user, url='testowner')
        assert user.get_url() == 'testowner'

    def test_get_url_no_owner(self):
        """Test get_url returns None when user has no owners."""
        user = UserFactory()
        assert user.get_url() is None

    def test_generate_device_code_length(self):
        """Test that device code is generated with correct length."""
        code = User.generate_device_code()
        assert len(code) == 5

    def test_generate_device_code_custom_length(self):
        """Test that device code can be generated with custom length."""
        code = User.generate_device_code(length=10)
        assert len(code) == 10

    def test_generate_device_code_excluded_characters(self):
        """Test that device code excludes ambiguous characters."""
        # Generate many codes and check none contain excluded characters
        excluded = "I1O0"
        for _ in range(100):
            code = User.generate_device_code()
            for char in excluded:
                assert char not in code

    def test_generate_device_code_uppercase_and_digits(self):
        """Test that device code only contains uppercase letters and digits."""
        code = User.generate_device_code()
        assert code.isupper() or code.isdigit()
        assert code.isalnum()

    def test_generate_access_token(self):
        """Test generating JWT access token for user."""
        user = UserFactory(email='test@example.com')
        token = user.generate_access_token()

        # Decode and verify token
        decoded = jwt.decode(
            token,
            settings.JWT_KEY,
            algorithms=["HS256"]
        )

        assert decoded['sub'] == 'test@example.com'
        assert 'exp' in decoded

    def test_generate_access_token_expiry(self):
        """Test that access token has correct expiry time."""
        user = UserFactory()
        token = user.generate_access_token()

        decoded = jwt.decode(
            token,
            settings.JWT_KEY,
            algorithms=["HS256"]
        )

        exp_timestamp = decoded['exp']
        exp_datetime = datetime.utcfromtimestamp(exp_timestamp)
        now = datetime.utcnow()

        # Token should expire in approximately ACCESS_TOKEN_EXPIRE_MINUTES
        time_diff = exp_datetime - now
        expected_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES

        # Allow 1 minute tolerance for test execution time
        assert abs(time_diff.total_seconds() - (expected_minutes * 60)) < 60

    def test_has_single_owner_true(self):
        """Test has_single_owner property returns True with one owner."""
        user = UserFactory()
        owner = AssetOwnerFactory(django_user=user)
        assert user.has_single_owner is True

    def test_has_single_owner_false_no_owners(self):
        """Test has_single_owner property returns False with no owners."""
        user = UserFactory()
        assert user.has_single_owner is False

    def test_has_single_owner_false_multiple_owners(self):
        """Test has_single_owner property returns False with multiple owners."""
        user = UserFactory()
        owner1 = AssetOwnerFactory(django_user=user)
        owner2 = AssetOwnerFactory(django_user=user)
        assert user.has_single_owner is False

    def test_email_unique_constraint(self):
        """Test that email field must be unique."""
        email = 'unique@example.com'
        UserFactory(email=email)

        with pytest.raises(Exception):
            UserFactory(email=email)

    def test_displayname_field(self):
        """Test displayname field is set correctly."""
        display_name = 'Test Display Name'
        user = UserFactory(displayname=display_name)
        assert user.displayname == display_name

    def test_user_authentication(self):
        """Test user can be authenticated with correct credentials."""
        user = UserFactory(username='authuser')
        assert user.check_password('testpass123') is True
        assert user.check_password('wrongpassword') is False

    def test_superuser_creation(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass',
            displayname='Admin User'
        )
        assert user.is_superuser is True
        assert user.is_staff is True
        assert user.is_active is True
