import io
import os
import zipfile
from dataclasses import dataclass
from typing import List, Optional

from icosa.helpers.file import (
    add_thumbnail_to_asset,
    get_content_type,
    validate_file,
)
from icosa.models import (
    ASSET_STATE_COMPLETE,
    Asset,
    AssetOwner,
    PolyFormat,
    PolyResource,
)
from ninja import File
from ninja.files import UploadedFile


@dataclass
class UploadSet:
    files: List[UploadedFile]
    manifest: Optional[UploadedFile] = None
    thumbnail: Optional[UploadedFile] = None


def process_files(files: List[UploadedFile]) -> UploadSet:
    thumbnail = None
    manifest = None
    unzipped_files = []
    for file in files:
        if not file.name.endswith(".zip"):
            # No further processing needed, though really we are not expecting
            # extra files outside of a zip.
            unzipped_files.append(file)
            continue

        # Read the file as a ZIP file
        with zipfile.ZipFile(io.BytesIO(file.read())) as zip_file:
            # Iterate over each file in the ZIP
            for zip_info in zip_file.infolist():
                # Skip directories
                if zip_info.is_dir():
                    continue
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
                        thumbnail = processed_file
                        continue
                    if manifest is None and filename.lower() == "manifest.json":
                        manifest = processed_file
                        continue
                    # Add the file to the list of unzipped files
                    # to process. Do not include the thumbnail or
                    # manifest.
                    unzipped_files.append(processed_file)
    return UploadSet(
        files=unzipped_files,
        manifest=manifest,
        thumbnail=thumbnail,
    )


# TODO(james): once this function and upload_api_asset have stabilised, the
# common parts should be abstracted out to reduce duplication.
def upload_api_asset(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    if files is None:
        files = []
    upload_set = process_files(files)
    print(upload_set)

    main_files = []
    sub_files = {
        "GLB": [],  # All non-thumbnail images.
        "GLTF": [],  # All GLB's files plus BIN files.
        "OBJ": [],  # MTL files.
        "FBX": [],  # FBM files.
    }
    asset_name = "Untitled Asset"

    sub_file_map = {
        "IMAGE": "GLB",
        "BIN": "GLTF",
        "MTL": "OBJ",
        "FBM": "FBX",
    }

    # 3. Create nested structure for roots and subs.
    # 4. Process manifest if it exists.

    for file in upload_set.files:
        splitext = os.path.splitext(file.name)
        extension = splitext[1].lower().replace(".", "")
        upload_details = validate_file(file, extension)
        if upload_details is not None:
            if upload_details.mainfile is True:
                main_files.append(upload_details)
                asset_name = splitext[0]
            else:
                parent_resource_type = sub_file_map[upload_details.filetype]
                sub_files[parent_resource_type].append(upload_details)

    # Begin upload process.

    asset.name = asset_name
    asset.save()

    for mainfile in main_files:
        type = mainfile.filetype
        if type.startswith("GLTF"):
            sub_files_list = sub_files["GLTF"] + sub_files["GLB"]
        else:
            try:
                sub_files_list = sub_files[type]
            except KeyError:
                sub_files_list = []
        make_formats(
            mainfile,
            sub_files_list,
            asset,
        )

    if upload_set.thumbnail:
        add_thumbnail_to_asset(upload_set.thumbnail, asset)

    asset.state = ASSET_STATE_COMPLETE
    asset.save()
    return asset


def make_formats(mainfile, sub_files, asset):
    # Main files determine folder
    format_type = mainfile.filetype
    file = mainfile.file
    name = mainfile.file.name

    format_data = {
        "format_type": format_type,
        "asset": asset,
    }
    format = PolyFormat.objects.create(**format_data)

    resource_data = {
        "file": file,
        "is_root": True,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(name),
    }
    PolyResource.objects.create(**resource_data)

    for subfile in sub_files:
        sub_resource_data = {
            "file": subfile.file,
            "format": format,
            "is_root": False,
            "asset": asset,
            "contenttype": get_content_type(subfile.file.name),
        }
        PolyResource.objects.create(**sub_resource_data)

    format.save()  # Triggers denorming on Format
