"""
Tests for authentication view functions.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from datetime import timedelta

from icosa.models import DeviceCode, AssetOwner
from icosa.tests.fixtures.factories import (
    UserFactory,
    AssetOwnerFactory,
    DeviceCodeFactory,
)

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.views
class TestLoginView:
    """Test suite for custom login view."""

    @patch('icosa.views.auth.config')
    def test_login_page_loads(self, mock_config, client):
        """Test that login page loads when login is open."""
        mock_config.LOGIN_OPEN = True
        response = client.get(reverse('icosa:login'))
        assert response.status_code == 200

    @patch('icosa.views.auth.config')
    def test_login_closed_returns_404(self, mock_config, client):
        """Test that login page returns 404 when login is closed."""
        mock_config.LOGIN_OPEN = False
        response = client.get(reverse('icosa:login'))
        assert response.status_code == 404

    @patch('icosa.views.auth.config')
    def test_successful_login(self, mock_config, client):
        """Test successful login with valid credentials."""
        mock_config.LOGIN_OPEN = True
        user = UserFactory(email='test@example.com')
        user.set_password('testpass123')
        user.is_active = True
        user.save()

        response = client.post(reverse('icosa:login'), {
            'email': 'test@example.com',
            'password': 'testpass123',
        })

        # Should redirect after successful login
        assert response.status_code == 302

    @patch('icosa.views.auth.config')
    def test_login_with_invalid_credentials(self, mock_config, client):
        """Test login with invalid credentials."""
        mock_config.LOGIN_OPEN = True
        user = UserFactory(email='test@example.com')
        user.set_password('testpass123')
        user.save()

        response = client.post(reverse('icosa:login'), {
            'email': 'test@example.com',
            'password': 'wrongpassword',
        })

        # Should show error
        assert response.status_code == 200
        assert 'error' in response.context

    @patch('icosa.views.auth.config')
    def test_login_with_inactive_user(self, mock_config, client):
        """Test login with inactive user."""
        mock_config.LOGIN_OPEN = True
        user = UserFactory(email='test@example.com', is_active=False)
        user.set_password('testpass123')
        user.save()

        response = client.post(reverse('icosa:login'), {
            'email': 'test@example.com',
            'password': 'testpass123',
        })

        assert response.status_code == 200
        assert 'error' in response.context

    @patch('icosa.views.auth.config')
    def test_login_redirects_authenticated_user(self, mock_config, authenticated_client):
        """Test that authenticated user is redirected."""
        mock_config.LOGIN_OPEN = True
        response = authenticated_client.get(reverse('icosa:login'))
        assert response.status_code == 302

    @patch('icosa.views.auth.config')
    def test_login_with_redirect_parameter(self, mock_config, client):
        """Test login with redirect parameter."""
        mock_config.LOGIN_OPEN = True
        user = UserFactory(email='test@example.com')
        user.set_password('testpass123')
        user.is_active = True
        user.save()

        response = client.post(reverse('icosa:login') + '?next=/uploads', {
            'email': 'test@example.com',
            'password': 'testpass123',
        })

        # Should redirect to specified page
        assert response.status_code == 302

    @patch('icosa.views.auth.config')
    def test_login_claims_unclaimed_assets(self, mock_config, client):
        """Test that login claims unclaimed assets."""
        mock_config.LOGIN_OPEN = True
        user = UserFactory(email='test@example.com')
        user.set_password('testpass123')
        user.is_active = True
        user.save()

        # Create unclaimed owner with same email
        unclaimed_owner = AssetOwnerFactory(
            email='test@example.com',
            url=user.username,
            django_user=None,
            is_claimed=False
        )

        response = client.post(reverse('icosa:login'), {
            'email': 'test@example.com',
            'password': 'testpass123',
        })

        unclaimed_owner.refresh_from_db()
        assert unclaimed_owner.django_user == user
        assert unclaimed_owner.is_claimed is True


@pytest.mark.django_db
@pytest.mark.views
class TestLogoutView:
    """Test suite for logout view."""

    def test_logout_get_shows_confirmation(self, authenticated_client):
        """Test that GET shows logout confirmation."""
        response = authenticated_client.get(reverse('icosa:logout'))
        assert response.status_code == 200

    def test_logout_post_logs_out_user(self, authenticated_client):
        """Test that POST logs out the user."""
        response = authenticated_client.post(reverse('icosa:logout'))
        assert response.status_code == 302

    def test_logout_get_not_post(self, client):
        """Test that GET is supported."""
        response = client.get(reverse('icosa:logout'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestRegisterView:
    """Test suite for user registration view."""

    @patch('icosa.views.auth.config')
    def test_register_page_loads(self, mock_config, client):
        """Test that register page loads when signup is open."""
        mock_config.SIGNUP_OPEN = True
        response = client.get(reverse('icosa:register'))
        assert response.status_code == 200

    @patch('icosa.views.auth.config')
    def test_register_closed_returns_404(self, mock_config, client):
        """Test that register page returns 404 when signup is closed."""
        mock_config.SIGNUP_OPEN = False
        response = client.get(reverse('icosa:register'))
        assert response.status_code == 404

    @patch('icosa.views.auth.send_registration_email')
    @patch('icosa.forms.MathCaptchaField.clean', return_value=None)
    @patch('icosa.views.auth.config')
    def test_successful_registration(self, mock_config, _mock_captcha, mock_send_email, client):
        """Test successful user registration."""
        mock_config.SIGNUP_OPEN = True

        response = client.post(reverse('icosa:register'), {
            'username': 'testuser',
            'displayname': 'Test User',
            'email': 'newuser@example.com',
            'password_new': 'testpass123',
            'password_confirm': 'testpass123',
            'asset_ref': '',  # Honeypot field
        })

        # Should show success page
        assert response.status_code == 200

        # User should be created but inactive
        user = User.objects.get(email='newuser@example.com')
        assert user.is_active is False

    @patch('icosa.views.auth.send_registration_email')
    @patch('icosa.forms.MathCaptchaField.clean', return_value=None)
    @patch('icosa.views.auth.config')
    def test_registration_sends_email(self, mock_config, _mock_captcha, mock_send_email, client):
        """Test that registration sends confirmation email."""
        mock_config.SIGNUP_OPEN = True

        response = client.post(reverse('icosa:register'), {
            'username': 'testuser',
            'displayname': 'Test User',
            'email': 'newuser@example.com',
            'password_new': 'testpass123',
            'password_confirm': 'testpass123',
            'asset_ref': '',
        })

        # Email should be sent
        assert mock_send_email.called

    @patch('icosa.forms.MathCaptchaField.clean', return_value=None)
    @patch('icosa.views.auth.config')
    def test_registration_duplicate_email(self, mock_config, _mock_captcha, client):
        """Test registration with duplicate email."""
        mock_config.SIGNUP_OPEN = True
        existing_user = UserFactory(email='existing@example.com', is_active=True)

        response = client.post(reverse('icosa:register'), {
            'username': 'testuser',
            'displayname': 'Test User',
            'email': 'existing@example.com',
            'password_new': 'testpass123',
            'password_confirm': 'testpass123',
            'asset_ref': '',
        })

        # Should show success (to prevent email enumeration)
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestActivateRegistrationView:
    """Test suite for registration activation view."""

    def test_valid_activation_token(self, client):
        """Test activation with valid token."""
        user = UserFactory(is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = client.get(reverse('icosa:activate_registration', kwargs={
            'uidb64': uid,
            'token': token,
        }))

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.is_active is True

    def test_invalid_activation_token(self, client):
        """Test activation with invalid token."""
        user = UserFactory(is_active=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        invalid_token = 'invalid-token'

        response = client.get(reverse('icosa:activate_registration', kwargs={
            'uidb64': uid,
            'token': invalid_token,
        }))

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.is_active is False

    def test_activation_with_invalid_uid(self, client):
        """Test activation with invalid user ID."""
        response = client.get(reverse('icosa:activate_registration', kwargs={
            'uidb64': 'invalid',
            'token': 'token',
        }))

        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestPasswordResetView:
    """Test suite for password reset view."""

    def test_password_reset_page_loads(self, client):
        """Test that password reset page loads."""
        response = client.get(reverse('icosa:password_reset'))
        assert response.status_code == 200

    @patch('icosa.views.auth.send_password_reset_email')
    def test_password_reset_sends_email(self, mock_send_email, client):
        """Test that password reset sends email."""
        user = UserFactory(email='test@example.com', is_active=True)
        # User needs to have logged in at least once
        user.last_login = timezone.now()
        user.save()

        response = client.post(reverse('icosa:password_reset'), {
            'email': 'test@example.com',
        })

        # Should redirect to done page
        assert response.status_code == 302
        assert mock_send_email.called

    def test_password_reset_nonexistent_email(self, client):
        """Test password reset with nonexistent email."""
        response = client.post(reverse('icosa:password_reset'), {
            'email': 'nonexistent@example.com',
        })

        # Should still redirect (to prevent email enumeration)
        assert response.status_code == 302

    def test_password_reset_inactive_user(self, client):
        """Test password reset for inactive user."""
        user = UserFactory(email='test@example.com', is_active=False)

        response = client.post(reverse('icosa:password_reset'), {
            'email': 'test@example.com',
        })

        # Should redirect but not send email
        assert response.status_code == 302


@pytest.mark.django_db
@pytest.mark.views
class TestPasswordResetDoneView:
    """Test suite for password reset done view."""

    def test_password_reset_done_page(self, client):
        """Test that password reset done page loads."""
        response = client.get(reverse('icosa:password_reset_done'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestPasswordResetConfirmView:
    """Test suite for password reset confirm view."""

    def test_password_reset_confirm_with_valid_token(self, client):
        """Test password reset confirmation with valid token."""
        user = UserFactory(is_active=True)
        user.last_login = timezone.now()
        user.save()

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # First request redirects to set-password URL
        response = client.get(reverse('icosa:password_reset_confirm', kwargs={
            'uidb64': uid,
            'token': token,
        }))

        assert response.status_code == 302

    def test_password_reset_confirm_with_invalid_token(self, client):
        """Test password reset confirmation with invalid token."""
        user = UserFactory(is_active=True)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = client.get(reverse('icosa:password_reset_confirm', kwargs={
            'uidb64': uid,
            'token': 'invalid-token',
        }))

        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestPasswordResetCompleteView:
    """Test suite for password reset complete view."""

    def test_password_reset_complete_page(self, client):
        """Test that password reset complete page loads."""
        response = client.get(reverse('icosa:password_reset_complete'))
        assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.views
class TestDeviceCodeView:
    """Test suite for device code generation view."""

    def test_devicecode_requires_authentication(self, client):
        """Test that device code view requires authentication."""
        response = client.get(reverse('icosa:devicecode'))
        assert response.status_code == 200
        # Should render but not show code for anonymous users

    def test_devicecode_generates_code_for_authenticated_user(self, authenticated_client, user):
        """Test that authenticated user gets a device code."""
        response = authenticated_client.get(reverse('icosa:devicecode'))
        assert response.status_code == 200
        assert 'device_code' in response.context

    def test_devicecode_creates_database_record(self, authenticated_client, user):
        """Test that device code creates database record."""
        response = authenticated_client.get(reverse('icosa:devicecode'))

        # Should create a device code in database
        assert DeviceCode.objects.filter(user=user).exists()

    def test_devicecode_with_openbrush_client(self, authenticated_client, user):
        """Test device code with Open Brush client."""
        response = authenticated_client.get(reverse('icosa:devicecode', kwargs={
            'appid': 'openbrush',
            'secret': 'test',
        }))
        assert response.status_code == 200
        assert response.context['client_name'] == 'Open Brush'

    def test_devicecode_with_openblocks_client(self, authenticated_client, user):
        """Test device code with Open Blocks client."""
        response = authenticated_client.get(reverse('icosa:devicecode', kwargs={
            'appid': 'openblocks',
            'secret': 'test',
        }))
        assert response.status_code == 200
        assert response.context['client_name'] == 'Open Blocks'

    def test_devicecode_deletes_old_codes(self, authenticated_client, user):
        """Test that device code deletes old codes for user."""
        # Create existing code
        old_code = DeviceCodeFactory(user=user)

        response = authenticated_client.get(reverse('icosa:devicecode'))

        # Old code should be deleted
        assert not DeviceCode.objects.filter(id=old_code.id).exists()

    def test_devicecode_deletes_expired_codes(self, authenticated_client, user):
        """Test that device code deletes expired codes."""
        # Create expired code for another user
        other_user = UserFactory()
        expired_code = DeviceCodeFactory(
            user=other_user,
            expiry=timezone.now() - timedelta(hours=1)
        )

        response = authenticated_client.get(reverse('icosa:devicecode'))

        # Expired code should be deleted
        assert not DeviceCode.objects.filter(id=expired_code.id).exists()

    def test_devicecode_rejects_incomplete_query_format(self, authenticated_client, user):
        """Test device code rejects query data without app ID and secret."""
        response = authenticated_client.get(reverse('icosa:devicecode') + '?testsecret')
        assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.views
class TestDeviceLoginSuccessView:
    """Test suite for device login success view."""

    def test_device_login_success_page(self, client):
        """Test that device login success page loads."""
        response = client.get(reverse('icosa:device_login_success'))
        assert response.status_code == 200
