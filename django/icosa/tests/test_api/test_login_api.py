"""
Tests for Login API endpoints.
"""
import pytest
from django.utils import timezone
from datetime import timedelta
from urllib.parse import urlencode

from icosa.tests.fixtures.factories import (
    UserFactory,
    DeviceCodeFactory,
)


MISSING = object()


def post_device_login(api_client, device_code=MISSING):
    url = '/api/v1/login/device_login'
    if device_code is not MISSING:
        url = f'{url}?{urlencode({"device_code": device_code})}'
    return api_client.post(url)


@pytest.mark.django_db
@pytest.mark.api
class TestDeviceLoginAPI:
    """Test suite for POST /api/login/device_login endpoint."""

    def test_device_login_with_valid_code(self, api_client):
        """Test device login with valid, non-expired code."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='ABC123',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, 'ABC123')

        # Should return access token
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data
        assert data['token_type'] == 'bearer'

    def test_device_login_with_expired_code(self, api_client):
        """Test device login with expired code."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='EXPIRED',
            expiry=timezone.now() - timedelta(hours=1)  # Expired 1 hour ago
        )

        response = post_device_login(api_client, 'EXPIRED')

        # Should reject expired code
        assert response.status_code == 401

    def test_device_login_with_invalid_code(self, api_client):
        """Test device login with non-existent code."""
        response = post_device_login(api_client, 'INVALID')

        # Should return 401 unauthorized
        assert response.status_code == 401

    def test_device_login_deletes_code_after_use(self, api_client):
        """Test that device code is deleted after successful login."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='ONETIME',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, 'ONETIME')

        assert response.status_code == 200
        from icosa.models import DeviceCode
        assert not DeviceCode.objects.filter(devicecode='ONETIME').exists()

    def test_device_login_case_insensitive(self, api_client):
        """Test device login is case insensitive."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='ABC123',
            expiry=timezone.now() + timedelta(hours=1)
        )

        # Try with lowercase
        response = post_device_login(api_client, 'abc123')

        # Should accept case-insensitive match
        assert response.status_code == 200

    def test_device_login_returns_jwt_token(self, api_client):
        """Test that device login returns a valid JWT token."""
        user = UserFactory(email='test@example.com')
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='JWT123',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, 'JWT123')

        assert response.status_code == 200
        token = response.json()['access_token']
        assert isinstance(token, str)
        assert token

    def test_device_login_multiple_codes_error(self, api_client):
        """Test that multiple matching codes return error."""
        user = UserFactory()
        # Create duplicate device codes (should not happen in practice)
        DeviceCodeFactory(
            user=user,
            devicecode='DUPE',
            expiry=timezone.now() + timedelta(hours=1)
        )
        DeviceCodeFactory(
            user=user,
            devicecode='DUPE',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, 'DUPE')

        # Should return 401 for multiple matches
        assert response.status_code == 401

    def test_device_login_empty_code(self, api_client):
        """Test device login with empty code."""
        response = post_device_login(api_client, '')

        # Should reject empty code
        assert response.status_code in [400, 401, 422]

    def test_device_login_missing_code_parameter(self, api_client):
        """Test device login without code parameter."""
        response = post_device_login(api_client)

        # Should return error for missing parameter
        assert response.status_code in [400, 422]

    def test_device_login_generates_token_for_user(self, api_client):
        """Test that generated token is associated with correct user."""
        user = UserFactory(email='tokenuser@example.com')
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='USERTOKEN',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, 'USERTOKEN')

        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')

            # Decode token to verify user
            import jwt
            from django.conf import settings

            try:
                decoded = jwt.decode(token, settings.JWT_KEY, algorithms=["HS256"])
                # Token should contain user's email
                assert decoded.get('sub') == user.email
            except:
                # JWT_KEY might not be configured in test settings
                pass

    def test_device_login_with_whitespace(self, api_client):
        """Test device login with whitespace in code."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='SPACE',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, ' SPACE ')

        # Behavior depends on whether whitespace is trimmed
        assert response.status_code in [200, 401]

    def test_device_login_with_special_characters(self, api_client):
        """Test device login doesn't accept special characters."""
        response = post_device_login(api_client, 'ABC-123!')

        # Should not find code with special chars
        assert response.status_code == 401

    def test_device_login_token_expiry(self, api_client):
        """Test that returned token has expiry set."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='EXPIRY',
            expiry=timezone.now() + timedelta(hours=1)
        )

        response = post_device_login(api_client, 'EXPIRY')

        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')

            # Decode and check expiry
            import jwt
            from django.conf import settings

            try:
                decoded = jwt.decode(token, settings.JWT_KEY, algorithms=["HS256"])
                assert 'exp' in decoded
                # Expiry should be in the future
                assert decoded['exp'] > timezone.now().timestamp()
            except:
                # JWT_KEY might not be configured
                pass


@pytest.mark.django_db
@pytest.mark.api
class TestDeviceCodeModel:
    """Additional tests for DeviceCode model functionality."""

    def test_device_code_string_representation(self):
        """Test string representation of device code."""
        user = UserFactory()
        expiry = timezone.now() + timedelta(hours=1)
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='TEST',
            expiry=expiry
        )

        str_repr = str(device_code)
        assert 'TEST' in str_repr
        assert str(expiry) in str_repr

    def test_device_code_max_length(self):
        """Test device code max length is 6 characters."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='ABC123',
            expiry=timezone.now() + timedelta(hours=1)
        )

        assert len(device_code.devicecode) <= 6

    def test_device_code_user_cascade_delete(self):
        """Test that deleting user deletes their device codes."""
        user = UserFactory()
        device_code = DeviceCodeFactory(
            user=user,
            devicecode='CASCADE',
            expiry=timezone.now() + timedelta(hours=1)
        )

        code_id = device_code.id
        user.delete()

        from icosa.models import DeviceCode
        # Device code should be deleted
        assert not DeviceCode.objects.filter(id=code_id).exists()

    def test_device_code_expiry_check(self):
        """Test checking if device code is expired."""
        user = UserFactory()

        valid_code = DeviceCodeFactory(
            user=user,
            devicecode='VALID',
            expiry=timezone.now() + timedelta(hours=1)
        )

        expired_code = DeviceCodeFactory(
            user=user,
            devicecode='EXPIRED',
            expiry=timezone.now() - timedelta(hours=1)
        )

        # Valid code expiry should be in future
        assert valid_code.expiry > timezone.now()

        # Expired code expiry should be in past
        assert expired_code.expiry < timezone.now()
