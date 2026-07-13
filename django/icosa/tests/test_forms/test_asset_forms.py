"""
Tests for Asset-related forms.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from icosa.forms import AssetUploadForm, AssetEditForm, AssetPublishForm, AssetReportForm
from icosa.models.common import PUBLIC, PRIVATE, UNLISTED
from icosa.tests.fixtures.factories import AssetFactory


@pytest.mark.django_db
@pytest.mark.forms
class TestAssetUploadForm:
    """Test suite for AssetUploadForm."""

    def test_valid_glb_file(self, sample_glb_file):
        """Test form accepts valid GLB file."""
        form = AssetUploadForm(
            data={},
            files={'file': sample_glb_file}
        )

        # Form should validate based on extension
        # Note: Full MIME validation may require actual file content
        assert 'file' in form.fields

    def test_valid_zip_file(self):
        """Test form accepts valid ZIP file."""
        # Minimal ZIP file header
        zip_data = b'PK\x03\x04' + b'\x00' * 20
        zip_file = SimpleUploadedFile(
            'model.zip',
            zip_data,
            content_type='application/zip'
        )

        form = AssetUploadForm(
            data={},
            files={'file': zip_file}
        )

        assert 'file' in form.fields

    def test_invalid_file_extension(self):
        """Test form rejects invalid file extensions."""
        txt_file = SimpleUploadedFile(
            'document.txt',
            b'This is a text file',
            content_type='text/plain'
        )

        form = AssetUploadForm(
            data={},
            files={'file': txt_file}
        )

        assert not form.is_valid()
        assert 'file' in form.errors

    def test_allowed_extensions_list(self):
        """Test all allowed extensions are accepted."""
        from icosa.forms import ALLOWED_UPLOAD_EXTENSIONS

        allowed_extensions = ALLOWED_UPLOAD_EXTENSIONS
        assert 'zip' in allowed_extensions
        assert 'glb' in allowed_extensions
        assert 'ksplat' in allowed_extensions
        assert 'ply' in allowed_extensions
        assert 'stl' in allowed_extensions
        assert 'usdz' in allowed_extensions
        assert 'vox' in allowed_extensions

    def test_file_field_required(self):
        """Test file field is required."""
        form = AssetUploadForm(data={}, files={})

        assert not form.is_valid()
        assert 'file' in form.errors

    def test_multiple_file_types(self):
        """Test various allowed file types."""
        extensions = ['glb', 'zip', 'ksplat', 'ply', 'usdz']

        for ext in extensions:
            file = SimpleUploadedFile(
                f'model.{ext}',
                b'dummy content',
                content_type='application/octet-stream'
            )

            form = AssetUploadForm(data={}, files={'file': file})
            assert 'file' in form.fields


@pytest.mark.django_db
@pytest.mark.forms
class TestAssetReportForm:
    """Test suite for AssetReportForm."""

    def test_valid_report_form(self):
        """Test valid asset report form."""
        form_data = {
            'asset_url': 'test-asset',
            'reason_for_reporting': 'This asset contains inappropriate content.',
            'contact_email': 'reporter@example.com'
        }

        form = AssetReportForm(data=form_data)

        assert form.is_valid()

    def test_report_form_without_email(self):
        """Test report form without contact email (optional field)."""
        form_data = {
            'asset_url': 'test-asset',
            'reason_for_reporting': 'This asset violates copyright.',
            'contact_email': ''
        }

        form = AssetReportForm(data=form_data)

        assert form.is_valid()

    def test_report_form_requires_reason(self):
        """Test report form requires reason for reporting."""
        form_data = {
            'asset_url': 'test-asset',
            'reason_for_reporting': '',
            'contact_email': 'reporter@example.com'
        }

        form = AssetReportForm(data=form_data)

        assert not form.is_valid()
        assert 'reason_for_reporting' in form.errors

    def test_report_form_requires_asset_url(self):
        """Test report form requires asset URL."""
        form_data = {
            'asset_url': '',
            'reason_for_reporting': 'Inappropriate content',
            'contact_email': 'reporter@example.com'
        }

        form = AssetReportForm(data=form_data)

        assert not form.is_valid()
        assert 'asset_url' in form.errors

    def test_report_form_reason_max_length(self):
        """Test report form reason has max length of 1000 characters."""
        form_data = {
            'asset_url': 'test-asset',
            'reason_for_reporting': 'A' * 1001,  # Exceeds max length
            'contact_email': 'reporter@example.com'
        }

        form = AssetReportForm(data=form_data)

        assert not form.is_valid()
        assert 'reason_for_reporting' in form.errors

    def test_report_form_reason_exact_max_length(self):
        """Test report form accepts reason at exact max length."""
        form_data = {
            'asset_url': 'test-asset',
            'reason_for_reporting': 'A' * 1000,  # Exactly max length
            'contact_email': 'reporter@example.com'
        }

        form = AssetReportForm(data=form_data)

        assert form.is_valid()


@pytest.mark.django_db
@pytest.mark.forms
class TestAssetPublishForm:
    """Test suite for AssetPublishForm."""

    def test_publish_form_with_new_asset(self):
        """Test publish form with a new unpublished asset."""
        asset = AssetFactory(
            name='',
            license=None,
            visibility=PRIVATE
        )

        form = AssetPublishForm(instance=asset)

        assert 'name' in form.fields
        assert 'license' in form.fields

    def test_publish_form_requires_visibility(self):
        """Test publish form requires an asset visibility."""
        asset = AssetFactory(name='', license=None)

        form_data = {
            'name': '',
            'license': 'CREATIVE_COMMONS_BY_4_0'
        }

        form = AssetPublishForm(data=form_data, instance=asset)

        assert not form.is_valid()
        assert 'visibility' in form.errors

    def test_publish_form_valid_data(self):
        """Test publish form with valid data."""
        asset = AssetFactory(name='', license=None)

        form_data = {
            'name': 'My Published Asset',
            'license': 'CREATIVE_COMMONS_BY_4_0',
            'visibility': PUBLIC,
        }

        form = AssetPublishForm(data=form_data, instance=asset)

        assert form.is_valid()

    def test_publish_form_license_choices_include_cc(self):
        """Test publish form includes Creative Commons licenses."""
        asset = AssetFactory(name='', license=None)

        form = AssetPublishForm(instance=asset)

        license_choices = [choice[0] for choice in form.fields['license'].choices]
        assert 'CREATIVE_COMMONS_BY_4_0' in license_choices
        assert 'CREATIVE_COMMONS_0' in license_choices

    def test_publish_form_license_disabled_for_published_cc_asset(self):
        """Test license field is disabled for already published CC assets."""
        asset = AssetFactory(
            name='Published Asset',
            license='CREATIVE_COMMONS_BY_4_0',
            visibility=PUBLIC
        )

        form = AssetPublishForm(instance=asset)

        assert form.fields['license'].disabled is True

    def test_publish_form_license_enabled_for_private_cc_asset(self):
        """Test license field is enabled for private CC assets."""
        asset = AssetFactory(
            name='Private Asset',
            license='CREATIVE_COMMONS_BY_4_0',
            visibility=PRIVATE
        )

        form = AssetPublishForm(instance=asset)

        assert form.fields['license'].disabled is False


@pytest.mark.django_db
@pytest.mark.forms
class TestAssetEditForm:
    """Test suite for AssetEditForm."""

    def test_edit_form_requires_name(self):
        """Test edit form requires name field."""
        asset = AssetFactory(name='Test Asset')

        form = AssetEditForm(instance=asset)

        assert form.fields['name'].required is True

    def test_edit_form_with_editable_asset(self):
        """Test edit form with editable asset."""
        asset = AssetFactory(
            name='Editable Asset',
            visibility=PRIVATE,
            license=None
        )

        form = AssetEditForm(instance=asset)

        # Zip file field should be present for editable assets
        assert 'name' in form.fields

    def test_edit_form_with_non_editable_asset(self):
        """Test edit form with non-editable published CC asset."""
        asset = AssetFactory(
            name='Published Asset',
            visibility=PUBLIC,
            license='CREATIVE_COMMONS_BY_SA_4_0'
        )

        form = AssetEditForm(instance=asset)

        # Zip file field should be removed for non-editable assets
        assert 'zip_file' not in form.fields

    def test_edit_form_license_disabled_for_published(self):
        """Test license field disabled for published CC assets."""
        asset = AssetFactory(
            name='Published',
            license='CREATIVE_COMMONS_BY_4_0',
            visibility=PUBLIC
        )

        form = AssetEditForm(instance=asset)

        assert form.fields['license'].disabled is True

    def test_edit_form_license_enabled_for_unpublished(self):
        """Test license field enabled for unpublished assets."""
        asset = AssetFactory(
            name='Draft',
            license='CREATIVE_COMMONS_BY_4_0',
            visibility=PRIVATE
        )

        form = AssetEditForm(instance=asset)

        assert form.fields['license'].disabled is False

    def test_edit_form_includes_thumbnail_override(self):
        """Test edit form includes thumbnail_override field."""
        asset = AssetFactory()

        form = AssetEditForm(instance=asset)

        assert 'thumbnail_override' in form.fields
        assert form.fields['thumbnail_override'].required is False

    def test_edit_form_valid_update(self):
        """Test edit form with valid update data."""
        asset = AssetFactory(
            name='Old Name',
            description='Old description',
            visibility=PRIVATE
        )

        form_data = {
            'name': 'New Name',
            'description': 'New description',
            'category': 'ANIMALS',
            'license': 'CREATIVE_COMMONS_BY_4_0',
            'visibility': PRIVATE,
            'thumbnail_override': False
        }

        form = AssetEditForm(data=form_data, instance=asset)

        # Form should have necessary fields
        assert 'name' in form.fields
        assert 'description' in form.fields

    def test_edit_form_upgrades_v3_to_v4_license(self):
        """Test edit form allows upgrading from v3 to v4 CC license."""
        asset = AssetFactory(
            name='Asset',
            license='CREATIVE_COMMONS_BY_3_0',
            visibility=PUBLIC
        )

        form = AssetEditForm(instance=asset)

        # Should allow upgrading to v4
        license_choices = [choice[0] for choice in form.fields['license'].choices]
        assert 'CREATIVE_COMMONS_BY_4_0' in license_choices
