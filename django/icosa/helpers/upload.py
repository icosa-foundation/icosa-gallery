import io
import os
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import (
    List,
    Optional,
)

from django.utils import timezone
from icosa.api.exceptions import ZipException
from icosa.api.schema import AssetMetaData
from icosa.helpers.file import (
    MAX_UNZIP_BYTES,
    MAX_UNZIP_SECONDS,
    ProcessedUpload,
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
from ninja import Form
from ninja.errors import HttpError
from ninja.files import UploadedFile

DUMMY_EXTRACT_PATH = "/tmp"

ZIP_MAX_DEPTH = 7

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
    files: List[ProcessedUpload]
    thumbnail: Optional[ProcessedUpload] = None


def is_safe_zip_path(target_path, proposed_path):
    abs_target = os.path.abspath(target_path)
    abs_proposed = os.path.abspath(proposed_path)
    return abs_proposed.startswith(abs_target)


def process_files(files: List[UploadedFile]) -> UploadSet:
    # TODO(james): unify this with upload_web_ui.process_files
    # The two are similar and complex enough. Need to update the callsite of
    # the web_ui version. Prefer this version.
    thumbnail = None
    unzipped_files = []
    for file in files:
        if file.name is None:
            raise HttpError(400, "Unknown error with uploaded file.")
        if not file.name.endswith(".zip"):
            # Note, the mime type should be checked in the form if uploading
            # from the web. This function assumes the correct mime type for zip
            # or glb TODO: or binary file.
            processed_file = ProcessedUpload(
                file=file,
                full_path=file.name,
            )
            unzipped_files.append(processed_file)
            continue

        magic_bytes = next(file.chunks(chunk_size=2048))
        file.seek(0)
        if not validate_mime(magic_bytes, ["application/zip"]):
            raise HttpError(400, "Uploaded file is not a zip archive.")
        unzip_start = timezone.now()
        total_size_bytes = 0
        # Read the file as a ZIP file
        with zipfile.ZipFile(io.BytesIO(file.read())) as zip_file:
            for i, member in enumerate(zip_file.infolist()):
                # Protect against unbounded execution time (i.e) stop if it's
                # taking too long.
                unzip_elapsed = timezone.now() - unzip_start
                if unzip_elapsed.seconds > MAX_UNZIP_SECONDS:
                    raise ZipException("Zip taking too long to extract, aborting.")

                # Only allow 1000 "things" inside the zip. This includes
                # directories, even though we are skipping them. This is for
                # decompression safety.
                if i >= 999:
                    raise ZipException("Too many files")

                # Only allow unzipping files 7 directories deep.
                # Not a problem here, but a protection against unbounded
                # recursion elsewhere.
                depth = len(Path(member.filename).parents)
                if depth >= ZIP_MAX_DEPTH:
                    raise ZipException(f"Too many directory levels: {depth}.")

                # Protect against `Zip Slip` path traversal exploit.
                final_path = os.path.join(DUMMY_EXTRACT_PATH, member.filename)
                if not is_safe_zip_path(DUMMY_EXTRACT_PATH, final_path):
                    raise ZipException(f"Suspicious file path detected: {member.filename}.")

                # Protect, roughly, against unzipping extremely large things.
                total_size_bytes += member.file_size
                if total_size_bytes > MAX_UNZIP_BYTES:
                    raise ZipException(f"Uncompressed zip will be larger than {MAX_UNZIP_BYTES}")

                # Skip processing directories. This does not skip the
                # directories' files.
                if member.is_dir():
                    continue

                # Read the file contents
                with zip_file.open(member) as extracted_file:
                    # Create a new UploadedFile object
                    content = extracted_file.read()
                    filename = member.filename
                    processed_file = ProcessedUpload(
                        file=UploadedFile(
                            name=filename,
                            file=io.BytesIO(content),
                        ),
                        full_path=filename,
                    )
                    if thumbnail is None and filename.lower() in [
                        "thumbnail.png",
                        "thumbnail.jpg",
                        "thumbnail.jpeg",
                    ]:
                        # Only process one thumbnail file: the first one we
                        # find. All subsequent files passing this test will not
                        # be treated as thumbnails.
                        # NOTE: We cannot know if the first file that passes
                        # this test is a texture rather than a thumbnail.
                        # TODO: Perhaps we should warn the user about the above
                        # note.
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


async def upload_api_asset(
    asset: Asset,
    data: Optional[Form[AssetMetaData]] = None,
    files: Optional[List[UploadedFile]] = None,
):
    total_start = time.time()  # Logging

    asset.state = ASSET_STATE_UPLOADING
    await asset.asave()
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
    sub_files: dict[str, List[UploadedFormat]] = {
        "GLB": [],  # All non-thumbnail images.
        "GLTF": [],  # All GLB's files plus BIN files.
        "OBJ": [],  # MTL files.
        "FBX": [],  # FBM files.
    }
    asset_name = "Untitled Asset"

    for processed_file in upload_set.files:
        if processed_file.file.name is None:
            continue
        splitext = os.path.splitext(processed_file.file.name)
        extension = splitext[1].lower().replace(".", "")
        upload_details = validate_file(processed_file, extension)
        if upload_details is not None:
            if upload_details.mainfile is True:
                main_files.append(upload_details)
                asset_name = splitext[0]
            else:
                parent_resource_type = SUB_FILE_MAP[upload_details.filetype]
                sub_files[parent_resource_type].append(upload_details)

    # Begin upload process.

    asset.name = asset_name
    await asset.asave()

    tilt_or_blocks = None
    for mainfile in main_files:
        if mainfile.filetype == "TILT":
            tilt_or_blocks = "tilt"
            break
        if mainfile.filetype == "BLOCKS":
            tilt_or_blocks = "blocks"
            break

    format_overrides = get_format_overrides(data)
    print(f"XXX {timezone.now().strftime("%Y/%m/%d %H:%M:%S")} FORMAT_OVERRIDES: {format_overrides}")
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

        await make_formats(
            mainfile,
            sub_files_list,
            asset,
            role,
            format_overrides,
        )

    if upload_set.thumbnail:
        await add_thumbnail_to_asset(upload_set.thumbnail, asset)

    await asset.asave()  # Denorm asset so far and save formats

    # Apply the one triangle count to all formats and resources.
    print(f"XXX {timezone.now().strftime("%Y/%m/%d %H:%M:%S")} DATA IS NONE: {data is None}")
    if data is not None:
        print(f"XXX {timezone.now().strftime("%Y/%m/%d %H:%M:%S")} DATA: {data}")
        formats = asset.format_set.all()
        async for fmt in formats:
            fmt.triangle_count = data.triangleCount
            await fmt.asave()

        asset.remix_ids = getattr(data, "remixIds", None)

    # TODO(james): We should move this blocks-related code into the flagship instance or trigger it some other way.
    print(f"XXX {timezone.now().strftime("%Y/%m/%d %H:%M:%S")} ASSET HAS BLOCKS: {asset.has_blocks}")
    if asset.has_blocks:
        preferred_format = await asset.format_set.filter(format_type="OBJ").afirst()
        if preferred_format is not None and preferred_format.root_resource and preferred_format.root_resource.file:
            preferred_format.is_preferred_for_gallery_viewer = True
            await preferred_format.asave()
    else:
        await asset.assign_preferred_viewer_format()
    print("XXX {timezone.now().strftime("%Y/%m/%d %H:%M:%S")} ASSIGNED VIEWER FORMAT")
    asset.state = ASSET_STATE_COMPLETE
    await asset.asave()

    total_end = time.time()  # Logging
    icosa_log(f"Finish uploading asset {asset.url} in {total_end - total_start} seconds.")  # Logging

    return asset


def get_format_overrides(data: Optional[AssetMetaData]):
    overrides = {}
    if data is not None and data.formatOverride is not None:
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


async def make_formats(mainfile, sub_files: List[UploadedFormat], asset, role, format_overrides):
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
    format = await Format.objects.acreate(**format_data)

    file_start = time.time()  # Logging

    root_resource_data = {
        "file": file,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(name),
    }
    root_resource = await Resource.objects.acreate(**root_resource_data)
    await format.aadd_root_resource(root_resource)
    await format.asave()

    file_end = time.time()  # Logging
    icosa_log(
        f"Finish processing file {file.name} for asset {asset.url} in {file_end - file_start} seconds."
    )  # Logging

    for subfile in sub_files:
        file_start = time.time()  # Logging

        sub_resource_data = {
            "uploaded_file_path": subfile.full_path,
            "format": format,
            "asset": asset,
            "contenttype": get_content_type(subfile.file.name),
        }
        resource = await Resource.objects.acreate(**sub_resource_data)
        resource.file = subfile.file
        await resource.asave()

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
    if mainfile.file.name is None:
        return role
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
