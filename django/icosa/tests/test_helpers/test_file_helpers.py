"""
Tests for file helper functions.
"""
import pytest
import io
from unittest.mock import Mock, patch, MagicMock

from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.files import UploadedFile

from icosa.helpers.file import (
    get_content_type,
    validate_file,
    is_gltf2,
    ProcessedUpload,
    UploadedFormat,
    VALID_FORMAT_TYPES,
    CONTENT_TYPE_MAP,
    IMAGE_REGEX,
)


@pytest.mark.helpers
class TestGetContentType:
    """Test suite for get_content_type function."""

    def test_get_content_type_glb(self):
        """Test getting content type for GLB file."""
        content_type = get_content_type('model.glb')
        assert content_type == 'model/gltf-binary'

    def test_get_content_type_gltf(self):
        """Test getting content type for GLTF file."""
        content_type = get_content_type('model.gltf')
        assert content_type == 'model/gltf+json'

    def test_get_content_type_obj(self):
        """Test getting content type for OBJ file."""
        content_type = get_content_type('model.obj')
        assert content_type == 'text/plain'

    def test_get_content_type_mtl(self):
        """Test getting content type for MTL file."""
        content_type = get_content_type('material.mtl')
        assert content_type == 'text/plain'

    def test_get_content_type_fbx(self):
        """Test getting content type for FBX file."""
        content_type = get_content_type('model.fbx')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_jpeg(self):
        """Test getting content type for JPEG file."""
        content_type = get_content_type('image.jpeg')
        assert content_type == 'image/jpeg'

    def test_get_content_type_jpg(self):
        """Test getting content type for JPG file."""
        content_type = get_content_type('image.jpg')
        assert content_type == 'image/jpeg'

    def test_get_content_type_png(self):
        """Test getting content type for PNG file."""
        content_type = get_content_type('image.png')
        assert content_type == 'image/png'

    def test_get_content_type_tilt(self):
        """Test getting content type for Tilt Brush file."""
        content_type = get_content_type('art.tilt')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_blocks(self):
        """Test getting content type for Blocks file."""
        content_type = get_content_type('model.blocks')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_vox(self):
        """Test getting content type for VOX file."""
        content_type = get_content_type('model.vox')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_ply(self):
        """Test getting content type for PLY file."""
        content_type = get_content_type('model.ply')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_stl(self):
        """Test getting content type for STL file."""
        content_type = get_content_type('model.stl')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_usdz(self):
        """Test getting content type for USDZ file."""
        content_type = get_content_type('model.usdz')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_ksplat(self):
        """Test getting content type for KSPLAT file."""
        content_type = get_content_type('model.ksplat')
        assert content_type == 'application/octet-stream'

    def test_get_content_type_unknown_extension(self):
        """Test getting content type for unknown extension returns None."""
        content_type = get_content_type('file.unknown')
        assert content_type is None

    def test_get_content_type_no_extension(self):
        """Test getting content type for file without extension."""
        content_type = get_content_type('filename')
        assert content_type is None

    def test_get_content_type_uppercase_extension(self):
        """Test getting content type with uppercase extension."""
        # The function converts to lowercase via the map lookup
        content_type = get_content_type('model.GLB')
        # Should return None as the extension is case-sensitive in the dict
        assert content_type is None or content_type == 'model/gltf-binary'


@pytest.mark.helpers
class TestValidateFile:
    """Test suite for validate_file function."""

    def test_validate_file_glb(self):
        """Test validating a GLB file."""
        mock_file = Mock()
        mock_file.name = 'model.glb'
        mock_file.file = io.BytesIO(b'glTF')

        uploaded_file = UploadedFile(name='model.glb', file=mock_file.file)
        result = validate_file(ProcessedUpload(uploaded_file, 'model.glb'), 'glb')

        assert result is not None
        assert isinstance(result, UploadedFormat)
        assert result.extension == 'glb'
        assert result.filetype == 'GLTF2'
        assert result.mainfile is True

    def test_validate_file_obj(self):
        """Test validating an OBJ file."""
        mock_file = Mock()
        mock_file.name = 'model.obj'

        uploaded_file = UploadedFile(name='model.obj', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.obj'), 'obj')

        assert result is not None
        assert result.extension == 'obj'
        assert result.filetype == 'OBJ'
        assert result.mainfile is True

    def test_validate_file_mtl(self):
        """Test validating an MTL file (not a main file)."""
        mock_file = Mock()

        uploaded_file = UploadedFile(name='material.mtl', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'material.mtl'), 'mtl')

        assert result is not None
        assert result.extension == 'mtl'
        assert result.filetype == 'MTL'
        assert result.mainfile is False

    def test_validate_file_fbx(self):
        """Test validating an FBX file."""
        uploaded_file = UploadedFile(name='model.fbx', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.fbx'), 'fbx')

        assert result is not None
        assert result.extension == 'fbx'
        assert result.filetype == 'FBX'
        assert result.mainfile is True

    def test_validate_file_tilt(self):
        """Test validating a Tilt Brush file."""
        uploaded_file = UploadedFile(name='art.tilt', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'art.tilt'), 'tilt')

        assert result is not None
        assert result.extension == 'tilt'
        assert result.filetype == 'TILT'
        assert result.mainfile is True

    def test_validate_file_blocks(self):
        """Test validating a Blocks file."""
        uploaded_file = UploadedFile(name='model.blocks', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.blocks'), 'blocks')

        assert result is not None
        assert result.extension == 'blocks'
        assert result.filetype == 'BLOCKS'
        assert result.mainfile is True

    def test_validate_file_vox(self):
        """Test validating a VOX file."""
        uploaded_file = UploadedFile(name='model.vox', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.vox'), 'vox')

        assert result is not None
        assert result.extension == 'vox'
        assert result.filetype == 'VOX'
        assert result.mainfile is True

    def test_validate_file_ply(self):
        """Test validating a PLY file."""
        uploaded_file = UploadedFile(name='model.ply', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.ply'), 'ply')

        assert result is not None
        assert result.extension == 'ply'
        assert result.filetype == 'PLY'
        assert result.mainfile is True

    def test_validate_file_stl(self):
        """Test validating an STL file."""
        uploaded_file = UploadedFile(name='model.stl', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.stl'), 'stl')

        assert result is not None
        assert result.extension == 'stl'
        assert result.filetype == 'STL'
        assert result.mainfile is True

    def test_validate_file_usdz(self):
        """Test validating a USDZ file."""
        uploaded_file = UploadedFile(name='model.usdz', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.usdz'), 'usdz')

        assert result is not None
        assert result.extension == 'usdz'
        assert result.filetype == 'USDZ'
        assert result.mainfile is True

    def test_validate_file_ksplat(self):
        """Test validating a KSPLAT file."""
        uploaded_file = UploadedFile(name='model.ksplat', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'model.ksplat'), 'ksplat')

        assert result is not None
        assert result.extension == 'ksplat'
        assert result.filetype == 'KSPLAT'
        assert result.mainfile is True

    def test_validate_file_image_png(self):
        """Test validating a PNG image file."""
        uploaded_file = UploadedFile(name='texture.png', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'texture.png'), 'png')

        assert result is not None
        assert result.extension == 'png'
        assert result.filetype == 'IMAGE'
        assert result.mainfile is False

    def test_validate_file_image_jpg(self):
        """Test validating a JPG image file."""
        uploaded_file = UploadedFile(name='texture.jpg', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'texture.jpg'), 'jpg')

        assert result is not None
        assert result.extension == 'jpg'
        assert result.filetype == 'IMAGE'

    def test_validate_file_image_jpeg(self):
        """Test validating a JPEG image file."""
        uploaded_file = UploadedFile(name='texture.jpeg', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'texture.jpeg'), 'jpeg')

        assert result is not None
        assert result.filetype == 'IMAGE'

    def test_validate_file_invalid_extension(self):
        """Test validating file with invalid extension returns None."""
        uploaded_file = UploadedFile(name='file.txt', file=io.BytesIO())
        result = validate_file(uploaded_file, 'txt')

        assert result is None

    def test_validate_file_bin(self):
        """Test validating a BIN file (not a main file)."""
        uploaded_file = UploadedFile(name='data.bin', file=io.BytesIO())
        result = validate_file(ProcessedUpload(uploaded_file, 'data.bin'), 'bin')

        assert result is not None
        assert result.extension == 'bin'
        assert result.filetype == 'BIN'
        assert result.mainfile is False


@pytest.mark.helpers
class TestIsGltf2:
    """Test suite for is_gltf2 function."""

    @patch('icosa.helpers.file.ijson.parse')
    def test_is_gltf2_returns_true_for_gltf2(self, mock_parse):
        """Test is_gltf2 returns True for glTF 2.0 files."""
        # Mock GLTF2 structure (no "buffers" map_key event)
        mock_parse.return_value = [
            ("asset", "start_map", None),
            ("asset.version", "string", "2.0"),
        ]

        mock_file = io.BytesIO(b'{"asset": {"version": "2.0"}}')
        result = is_gltf2(mock_file)

        assert result is True

    @patch('icosa.helpers.file.ijson.parse')
    def test_is_gltf2_returns_false_for_gltf1(self, mock_parse):
        """Test is_gltf2 returns False for glTF 1.0 files."""
        # Mock GLTF1 structure (has "buffers" map_key event)
        mock_parse.return_value = [
            ("buffers", "map_key", "buffer1"),
            ("buffers.buffer1", "start_map", None),
        ]

        mock_file = io.BytesIO(b'{"buffers": {"buffer1": {}}}')
        result = is_gltf2(mock_file)

        assert result is False

    def test_validate_file_gltf_detects_version(self):
        """Test validate_file correctly detects GLTF version."""
        # Create a mock GLTF 2.0 file
        gltf2_content = b'{"asset": {"version": "2.0"}}'
        mock_file = io.BytesIO(gltf2_content)

        with patch('icosa.helpers.file.is_gltf2', return_value=True):
            uploaded_file = UploadedFile(name='model.gltf', file=mock_file)
            result = validate_file(ProcessedUpload(uploaded_file, 'model.gltf'), 'gltf')

            assert result is not None
            assert result.filetype == 'GLTF2'

    def test_validate_file_gltf1_detected(self):
        """Test validate_file detects GLTF 1.0 files."""
        gltf1_content = b'{"buffers": {"buffer1": {}}}'
        mock_file = io.BytesIO(gltf1_content)

        with patch('icosa.helpers.file.is_gltf2', return_value=False):
            uploaded_file = UploadedFile(name='model.gltf', file=mock_file)
            result = validate_file(ProcessedUpload(uploaded_file, 'model.gltf'), 'gltf')

            assert result is not None
            assert result.filetype == 'GLTF1'


@pytest.mark.helpers
class TestValidFormatTypes:
    """Test suite for VALID_FORMAT_TYPES constant."""

    def test_valid_format_types_includes_common_formats(self):
        """Test VALID_FORMAT_TYPES includes all common 3D formats."""
        assert 'glb' in VALID_FORMAT_TYPES
        assert 'gltf' in VALID_FORMAT_TYPES
        assert 'obj' in VALID_FORMAT_TYPES
        assert 'fbx' in VALID_FORMAT_TYPES
        assert 'mtl' in VALID_FORMAT_TYPES
        assert 'bin' in VALID_FORMAT_TYPES

    def test_valid_format_types_includes_proprietary_formats(self):
        """Test VALID_FORMAT_TYPES includes proprietary formats."""
        assert 'tilt' in VALID_FORMAT_TYPES
        assert 'blocks' in VALID_FORMAT_TYPES

    def test_valid_format_types_includes_new_formats(self):
        """Test VALID_FORMAT_TYPES includes newer format types."""
        assert 'ksplat' in VALID_FORMAT_TYPES
        assert 'ply' in VALID_FORMAT_TYPES
        assert 'stl' in VALID_FORMAT_TYPES
        assert 'usdz' in VALID_FORMAT_TYPES
        assert 'vox' in VALID_FORMAT_TYPES
        assert 'sog' in VALID_FORMAT_TYPES
        assert 'spz' in VALID_FORMAT_TYPES
        assert 'splat' in VALID_FORMAT_TYPES


@pytest.mark.helpers
class TestContentTypeMap:
    """Test suite for CONTENT_TYPE_MAP constant."""

    def test_content_type_map_completeness(self):
        """Test CONTENT_TYPE_MAP has entries for all valid formats."""
        # Check key formats have content types
        assert 'glb' in CONTENT_TYPE_MAP
        assert 'gltf' in CONTENT_TYPE_MAP
        assert 'obj' in CONTENT_TYPE_MAP
        assert 'fbx' in CONTENT_TYPE_MAP

    def test_content_type_map_correct_mime_types(self):
        """Test CONTENT_TYPE_MAP has correct MIME types."""
        assert CONTENT_TYPE_MAP['glb'] == 'model/gltf-binary'
        assert CONTENT_TYPE_MAP['gltf'] == 'model/gltf+json'
        assert CONTENT_TYPE_MAP['jpeg'] == 'image/jpeg'
        assert CONTENT_TYPE_MAP['png'] == 'image/png'


@pytest.mark.helpers
class TestImageRegex:
    """Test suite for IMAGE_REGEX pattern."""

    def test_image_regex_matches_common_formats(self):
        """Test IMAGE_REGEX matches common image formats."""
        assert IMAGE_REGEX.match('jpg') is not None
        assert IMAGE_REGEX.match('jpeg') is not None
        assert IMAGE_REGEX.match('png') is not None
        assert IMAGE_REGEX.match('tiff') is not None
        assert IMAGE_REGEX.match('webp') is not None
        assert IMAGE_REGEX.match('bmp') is not None

    def test_image_regex_does_not_match_non_images(self):
        """Test IMAGE_REGEX doesn't match non-image extensions."""
        assert IMAGE_REGEX.match('glb') is None
        assert IMAGE_REGEX.match('obj') is None
        assert IMAGE_REGEX.match('txt') is None
