"""
Tests for the Format and Resource models.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from icosa.models import Format, Resource, FormatRoleLabel
from icosa.api.exceptions import RootResourceException
from icosa.tests.fixtures.factories import (
    AssetFactory,
    FormatFactory,
    GLBFormatFactory,
    OBJFormatFactory,
    FBXFormatFactory,
    ResourceFactory,
    FormatRoleLabelFactory,
)


@pytest.mark.django_db
@pytest.mark.models
class TestFormatModel:
    """Test suite for Format model."""

    def test_create_format(self):
        """Test creating a format with required fields."""
        format_instance = FormatFactory()
        assert format_instance.id is not None
        assert format_instance.asset is not None
        assert format_instance.format_type is not None

    def test_format_types(self):
        """Test creating formats with different types."""
        glb = GLBFormatFactory(format_type='GLB')
        obj = OBJFormatFactory(format_type='OBJ')
        fbx = FBXFormatFactory(format_type='FBX')

        assert glb.format_type == 'GLB'
        assert obj.format_type == 'OBJ'
        assert fbx.format_type == 'FBX'

    def test_format_role_field(self):
        """Test format role field."""
        format_instance = FormatFactory(role='ORIGINAL_GLTF_FORMAT')
        assert format_instance.role == 'ORIGINAL_GLTF_FORMAT'

    def test_triangle_count_field(self):
        """Test triangle_count field."""
        format_instance = FormatFactory(triangle_count=5000)
        assert format_instance.triangle_count == 5000

    def test_lod_hint_field(self):
        """Test lod_hint field."""
        format_instance = FormatFactory(lod_hint=2)
        assert format_instance.lod_hint == 2

    def test_zip_archive_url_field(self):
        """Test zip_archive_url field."""
        format_instance = FormatFactory(zip_archive_url='https://example.com/archive.zip')
        assert format_instance.zip_archive_url == 'https://example.com/archive.zip'

    def test_is_preferred_for_gallery_viewer(self):
        """Test is_preferred_for_gallery_viewer flag."""
        format_instance = FormatFactory(is_preferred_for_gallery_viewer=True)
        assert format_instance.is_preferred_for_gallery_viewer is True

    def test_is_preferred_for_download(self):
        """Test is_preferred_for_download flag."""
        format_instance = FormatFactory(is_preferred_for_download=False)
        assert format_instance.is_preferred_for_download is False

    def test_add_root_resource_success(self):
        """Test add_root_resource sets root resource correctly."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)
        resource = ResourceFactory(asset=asset, format=format_instance)

        format_instance.add_root_resource(resource)

        format_instance.refresh_from_db()
        resource.refresh_from_db()

        assert format_instance.root_resource == resource
        assert resource.format is None

    def test_add_root_resource_without_format_raises_exception(self):
        """Test add_root_resource raises exception if resource has no format."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)
        resource = ResourceFactory(asset=asset, format=None)

        with pytest.raises(RootResourceException):
            format_instance.add_root_resource(resource)

    def test_get_all_resources_with_root(self):
        """Test get_all_resources returns all resources including root."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)

        # Create regular resources
        resource1 = ResourceFactory(asset=asset, format=format_instance)
        resource2 = ResourceFactory(asset=asset, format=format_instance)

        # Set root resource
        root_resource = ResourceFactory(asset=asset, format=format_instance)
        format_instance.add_root_resource(root_resource)

        resources = format_instance.get_all_resources()

        # Should include both regular resources and root resource
        assert resource1 in resources
        assert resource2 in resources
        # Note: root_resource should be included through the union

    def test_get_all_resources_without_root(self):
        """Test get_all_resources when there's no root resource."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)

        resource1 = ResourceFactory(asset=asset, format=format_instance)
        resource2 = ResourceFactory(asset=asset, format=format_instance)

        resources = format_instance.get_all_resources()

        assert resource1 in resources
        assert resource2 in resources

    def test_get_resource_data_all_cors_allowed(self):
        """Test get_resource_data when all resources are CORS allowed."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)

        # Mock resources with external URLs
        resource1 = Mock()
        resource1.is_cors_allowed = True
        resource1.remote_host = 'example.com'
        resource1.external_url = 'https://example.com/file1.glb'
        resource1.file = None

        resource2 = Mock()
        resource2.is_cors_allowed = True
        resource2.remote_host = 'example.com'
        resource2.external_url = 'https://example.com/file2.png'
        resource2.file = None

        resources = [resource1, resource2]
        resource_data = format_instance.get_resource_data(resources)

        assert 'files_to_zip' in resource_data
        assert len(resource_data['files_to_zip']) == 2

    def test_get_resource_data_all_local_files(self):
        """Test get_resource_data when all resources are local files."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)

        # Mock resources with files
        resource1 = Mock()
        resource1.file = Mock()
        resource1.file.name = 'path/to/file1.glb'
        resource1.external_url = None
        resource1.uploaded_file_path = None

        resource2 = Mock()
        resource2.file = Mock()
        resource2.file.name = 'path/to/file2.png'
        resource2.external_url = None
        resource2.uploaded_file_path = None

        resources = [resource1, resource2]
        resource_data = format_instance.get_resource_data(resources)

        assert 'files_to_zip' in resource_data
        assert len(resource_data['files_to_zip']) == 2

    def test_get_resource_data_mixed_returns_empty(self):
        """Test get_resource_data returns empty dict for mixed resources."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)

        # Mock resources with mixed types
        resource1 = Mock()
        resource1.file = Mock()
        resource1.file.name = 'path/to/file1.glb'
        resource1.external_url = None
        resource1.uploaded_file_path = None

        resource2 = Mock()
        resource2.is_cors_allowed = False
        resource2.remote_host = 'example.com'
        resource2.external_url = 'https://example.com/file2.png'
        resource2.file = None

        resources = [resource1, resource2]
        resource_data = format_instance.get_resource_data(resources)

        assert resource_data == {}

    def test_user_label_with_role_label(self):
        """Test user_label returns formatted label when role label exists."""
        role_label = FormatRoleLabelFactory(
            role_text='ORIGINAL_GLTF_FORMAT',
            label='Original glTF'
        )
        format_instance = FormatFactory(role='ORIGINAL_GLTF_FORMAT')

        label = format_instance.user_label()

        assert label == 'Original glTF'

    def test_user_label_without_role_label(self):
        """Test user_label returns format_type when no role label exists."""
        format_instance = FormatFactory(
            format_type='GLB',
            role='SOME_UNKNOWN_ROLE'
        )

        label = format_instance.user_label()

        assert label == 'glb'

    def test_user_label_with_none_role(self):
        """Test user_label returns format_type when role is None."""
        format_instance = FormatFactory(format_type='GLB', role=None)

        label = format_instance.user_label()

        assert label == 'glb'

    def test_format_asset_relationship(self):
        """Test format belongs to an asset."""
        asset = AssetFactory()
        format_instance = FormatFactory(asset=asset)

        assert format_instance.asset == asset
        assert format_instance in asset.format_set.all()


@pytest.mark.django_db
@pytest.mark.models
class TestResourceModel:
    """Test suite for Resource model."""

    def test_create_resource(self):
        """Test creating a resource with required fields."""
        resource = ResourceFactory()
        assert resource.id is not None
        assert resource.asset is not None

    def test_resource_with_file(self):
        """Test resource with a file."""
        resource = ResourceFactory(
            file=None,
            contenttype='model/gltf-binary'
        )
        assert resource.contenttype == 'model/gltf-binary'

    def test_resource_with_external_url(self):
        """Test resource with external URL."""
        resource = ResourceFactory(
            external_url='https://example.com/model.glb',
            file=None
        )
        assert resource.external_url == 'https://example.com/model.glb'

    def test_url_property_with_file(self):
        """Test url property returns storage URL when file exists."""
        resource = ResourceFactory()
        resource.file = Mock()
        resource.file.name = 'path/to/model.glb'
        resource.external_url = None

        url = resource.url

        assert 'model.glb' in url

    def test_url_property_with_external_url(self):
        """Test url property returns external URL."""
        resource = ResourceFactory(
            external_url='https://example.com/model.glb',
            file=None
        )

        url = resource.url

        assert url == 'https://example.com/model.glb'

    def test_url_property_with_archive_url(self):
        """Test url property handles archive.org URLs correctly."""
        archive_url = 'https://web.archive.org/web/https://example.com/model.glb'
        resource = ResourceFactory(
            external_url=archive_url,
            file=None
        )

        url = resource.url

        assert url == archive_url

    def test_url_property_no_file_no_url(self):
        """Test url property returns empty string when no file or URL."""
        resource = ResourceFactory(file=None, external_url=None)

        url = resource.url

        assert url is None

    def test_relative_path_with_file(self):
        """Test relative_path returns filename from file path."""
        resource = ResourceFactory(format=None)
        resource.file = Mock()
        resource.file.name = 'path/to/model.glb'

        path = resource.relative_path

        assert path == 'model.glb'

    def test_relative_path_with_external_url(self):
        """Test relative_path returns filename from external URL."""
        resource = ResourceFactory(
            external_url='https://example.com/path/to/model.glb',
            file=None,
            format=None,
        )

        path = resource.relative_path

        assert path == 'model.glb'

    def test_remote_host_with_external_url(self):
        """Test remote_host extracts hostname from external URL."""
        resource = ResourceFactory(
            external_url='https://example.com/model.glb',
            file=None
        )

        host = resource.remote_host

        assert host == 'example.com'

    def test_remote_host_without_external_url(self):
        """Test remote_host returns None when no external URL."""
        resource = ResourceFactory(external_url=None)

        host = resource.remote_host

        assert host is None

    @patch('icosa.models.resource.get_cached_cors_allow_list', return_value='example.com, test.com')
    def test_is_cors_allowed_with_allowed_host(self, _mock_allow_list):
        """Test is_cors_allowed returns True for allowed hosts."""
        resource = ResourceFactory(
            external_url='https://example.com/model.glb',
            file=None
        )

        assert resource.is_cors_allowed is True

    @patch('icosa.models.resource.get_cached_cors_allow_list', return_value='example.com')
    def test_is_cors_allowed_with_disallowed_host(self, _mock_allow_list):
        """Test is_cors_allowed returns False for disallowed hosts."""
        resource = ResourceFactory(
            external_url='https://untrusted.com/model.glb',
            file=None
        )

        assert resource.is_cors_allowed is False

    def test_is_cors_allowed_local_file(self):
        """Test is_cors_allowed returns True for local files."""
        resource = ResourceFactory(external_url=None)
        resource.file = Mock()

        assert resource.is_cors_allowed is True

    def test_hide_from_downloads_field(self):
        """Test hide_from_downloads flag."""
        resource = ResourceFactory(hide_from_downloads=True)
        assert resource.hide_from_downloads is True


@pytest.mark.django_db
@pytest.mark.models
class TestFormatRoleLabelModel:
    """Test suite for FormatRoleLabel model."""

    def test_create_format_role_label(self):
        """Test creating a format role label."""
        label = FormatRoleLabelFactory(
            role_text='TEST_ROLE',
            label='Test Role Label'
        )

        assert label.role_text == 'TEST_ROLE'
        assert label.label == 'Test Role Label'
        assert label.create_time is not None

    def test_format_role_label_string_representation(self):
        """Test string representation of format role label."""
        label = FormatRoleLabelFactory(
            role_text='TEST_ROLE',
            label='Test Label'
        )

        assert str(label) == 'TEST_ROLE => Test Label'

    def test_format_role_label_timestamps(self):
        """Test create_time is set on creation."""
        label = FormatRoleLabelFactory()

        assert label.create_time is not None
        assert label.update_time is None
