import io
import os
import time
import zipfile
from dataclasses import dataclass
from typing import (
    List,
    Optional,
)

from django.utils import timezone
from ninja import Form
from ninja.errors import HttpError
from ninja.files import UploadedFile

from icosa.api.exceptions import ZipException
from icosa.api.schema import AssetMetaData
from icosa.helpers.file import (
    MAX_UNZIP_BYTES,
    MAX_UNZIP_SECONDS,
    UploadedFormat,
    add_thumbnail_to_asset,
    get_content_type,
    validate_file,
    validate_mime,
)
from icosa.helpers.logger import icosa_log
from icosa.models import (
    ASSET_STATE_COMPLETE,
    ASSET_STATE_UPLOADING,
    VALID_THUMBNAIL_MIME_TYPES,
    Asset,
    Format,
    Resource,
)

SUB_FILE_MAP = {
    "IMAGE": "GLB",
    "BIN": "GLTF",
    "MTL": "OBJ",
    "FBM": "FBX",
}

TYPE_ROLE_MAP = {
    "TILT": "TILT_FORMAT",
    "OBJ": "ORIGINAL_TRIANGULATED_OBJ_FORMAT",
    "FBX": "ORIGINAL_FBX_FORMAT",
    "GLB": "GLB_FORMAT",
}


@dataclass
class UploadSet:
    files: List[UploadedFile]
    thumbnail: Optional[UploadedFile] = None


def process_files(files: List[UploadedFile]) -> UploadSet:
    # TODO(james): unify this with upload_web_ui.process_files
    # The two are similar and complex enough. Need to update the callsite of
    # the web_ui version. Prefer this version.
    thumbnail = None
    unzipped_files = []
    for file in files:
        if not file.name.endswith(".zip"):
            # No further processing needed, though really we are not expecting
            # extra files outside of a zip.
            unzipped_files.append(file)
            continue

        magic_bytes = next(file.chunks(chunk_size=2048))
        file.seek(0)
        if not validate_mime(magic_bytes, ["application/zip"]):
            raise HttpError(400, "Uploaded file is not a zip archive.")
        unzip_start = timezone.now()
        total_size_bytes = 0
        # Read the file as a ZIP file
        with zipfile.ZipFile(io.BytesIO(file.read())) as zip_file:
            for i, zip_info in enumerate(zip_file.infolist()):
                unzip_elapsed = timezone.now() - unzip_start
                if unzip_elapsed.seconds > MAX_UNZIP_SECONDS:
                    raise ZipException("Zip taking too long to extract, aborting.")
                # only allow 1000 "things" inside the zip. This includes
                # directories, even though we are skipping them. This is for
                # decompression safety.
                if i >= 999:
                    raise ZipException("Too many files")
                # Skip directories
                # TODO(james): skipping directories is great for preventing zip
                # bombs, but isn't flexible.
                if zip_info.is_dir():
                    continue
                total_size_bytes += zip_info.file_size
                if total_size_bytes > MAX_UNZIP_BYTES:
                    raise ZipException(f"Uncompressed zip will be larger than {MAX_UNZIP_BYTES}")
                # Read the file contents
                with zip_file.open(zip_info) as extracted_file:
                    # Create a new UploadedFile object
                    content = extracted_file.read()
                    filename = zip_info.filename
                    processed_file = UploadedFile(
                        name=filename,
                        file=io.BytesIO(content),
                    )
                    if thumbnail is None and filename.lower() in [
                        "thumbnail.png",
                        "thumbnail.jpg",
                        "thumbnail.jpeg",
                    ]:
                        # Only process one thumbnail file: the first one
                        # we find. All other files passing this test will
                        # be ignored. This would go for textures named
                        # thumbnail.png if we already found a thumbnail.jpg.
                        # Unlikely, but possible.
                        if validate_mime(content, VALID_THUMBNAIL_MIME_TYPES):
                            thumbnail = processed_file
                            continue
                        else:
                            raise HttpError(400, "Thumbnail must be png or jpg.")
                    unzipped_files.append(processed_file)
    return UploadSet(
        files=unzipped_files,
        thumbnail=thumbnail,
    )


# TODO(james): once this function and upload_asset have stabilised, the
# common parts should be abstracted out to reduce duplication.
async def upload_api_asset(
    asset: Asset,
    data: Form[AssetMetaData],
    files: Optional[List[UploadedFile]] = None,
):
    total_start = time.time()  # Logging

    asset.state = ASSET_STATE_UPLOADING
    asset.save()
    if files is None:
        raise HttpError(400, "Include files for upload.")
    try:
        process_files_start = time.time()  # Logging
        upload_set = process_files(files)  # Logging
        process_files_end = time.time()
        icosa_log(
            f"Finish processing files for asset {asset.url} in {process_files_end - process_files_start} seconds."
        )  # Logging
    except (ZipException, HttpError):
        raise HttpError(400, "Invalid zip archive.")

    main_files = []
    sub_files = {
        "GLB": [],  # All non-thumbnail images.
        "GLTF": [],  # All GLB's files plus BIN files.
        "OBJ": [],  # MTL files.
        "FBX": [],  # FBM files.
    }
    asset_name = "Untitled Asset"

    for file in upload_set.files:
        splitext = os.path.splitext(file.name)
        extension = splitext[1].lower().replace(".", "")
        upload_details = validate_file(file, extension)
        if upload_details is not None:
            if upload_details.mainfile is True:
                main_files.append(upload_details)
                asset_name = splitext[0]
            else:
                parent_resource_type = SUB_FILE_MAP[upload_details.filetype]
                sub_files[parent_resource_type].append(upload_details)

    # Begin upload process.

    asset.name = asset_name
    asset.save()

    tilt_or_blocks = None
    for mainfile in main_files:
        if mainfile.filetype == "TILT":
            tilt_or_blocks = "tilt"
            break
        if mainfile.filetype == "BLOCKS":
            tilt_or_blocks = "blocks"
            break

    format_overrides = get_format_overrides(data)
    for mainfile in main_files:
        type = mainfile.filetype
        if type in ["GLTF1", "GLTF2"]:
            sub_files_list = sub_files["GLTF"] + sub_files["GLB"]
        else:
            try:
                sub_files_list = sub_files[type]
            except KeyError:
                sub_files_list = []

        role = get_role(
            mainfile,
            tilt_or_blocks,
        )

        make_formats(
            mainfile,
            sub_files_list,
            asset,
            role,
            format_overrides,
        )

    if upload_set.thumbnail:
        add_thumbnail_to_asset(upload_set.thumbnail, asset)

    asset.save()  # Denorm asset so far and save formats

    # Apply the one triangle count to all formats and resources.
    formats = asset.format_set.all()
    for fmt in formats:
        fmt.triangle_count = data.triangleCount
        fmt.save()

    asset.remix_ids = getattr(data, "remixIds", None)

    # TODO(james): We should move this blocks-related code into the flagship instance or trigger it some other way.
    if asset.has_blocks:
        preferred_format = asset.format_set.filter(format_type="OBJ").first()
        if preferred_format is not None and preferred_format.root_resource and preferred_format.root_resource.file:
            preferred_format.is_preferred_for_gallery_viewer = True
            preferred_format.save()
    else:
        await asset.assign_preferred_viewer_format()
    asset.state = ASSET_STATE_COMPLETE
    asset.save()

    total_end = time.time()  # Logging
    icosa_log(f"Finish uploading asset {asset.url} in {total_end - total_start} seconds.")  # Logging

    return asset


def get_format_overrides(data: AssetMetaData):
    overrides = {}
    if data.formatOverride is not None:
        for item in data.formatOverride:
            splt = item.split(":")
            if len(splt) == 2:
                filename = splt[0]
                format_override = splt[1]
            elif len(splt) > 2:
                filename = ":".join(splt[:-1])
                format_override = splt[-1]
            else:
                continue
            overrides.setdefault(filename, format_override)
    return overrides


def make_formats(mainfile, sub_files, asset, role, format_overrides):
    file = mainfile.file
    name = mainfile.file.name
    format_override = format_overrides.get(name)
    if format_override is None:
        format_type = mainfile.filetype
    else:
        format_type = format_override

    format_data = {
        "format_type": format_type,
        "asset": asset,
        "role": role,
    }
    format = Format.objects.create(**format_data)

    file_start = time.time()  # Logging

    root_resource_data = {
        "file": file,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(name),
    }
    root_resource = Resource.objects.create(**root_resource_data)
    format.add_root_resource(root_resource)
    format.save()

    file_end = time.time()  # Logging
    icosa_log(
        f"Finish processing file {file.name} for asset {asset.url} in {file_end - file_start} seconds."
    )  # Logging

    for subfile in sub_files:
        file_start = time.time()  # Logging

        sub_resource_data = {
            "file": subfile.file,
            "format": format,
            "asset": asset,
            "contenttype": get_content_type(subfile.file.name),
        }
        Resource.objects.create(**sub_resource_data)

        file_end = time.time()  # Logging
        icosa_log(
            f"Finish processing file {subfile.file.name} for asset {asset.url} in {file_end - file_start} seconds."
        )  # Logging


def get_role(
    mainfile: UploadedFormat,
    tilt_or_blocks: Optional[str] = None,
) -> str:
    filetype = mainfile.filetype
    role = ""
    if filetype in ["GLTF1", "GLTF2"]:
        if tilt_or_blocks == "tilt":
            role = "TILT_NATIVE_GLTF"
        else:
            role = "USER_SUPPLIED_GLTF"
    elif filetype == "OBJ" and tilt_or_blocks == "blocks":
        name = os.path.splitext(mainfile.file.name)[0]
        if name == "model-triangulated":
            role = "ORIGINAL_TRIANGULATED_OBJ_FORMAT"
        if name == "model":
            role = "ORIGINAL_OBJ_FORMAT"
    else:
        role = TYPE_ROLE_MAP.get(filetype, "")

    return role
