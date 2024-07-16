import io
import os
import re
import secrets
import zipfile
from dataclasses import dataclass
from typing import List, Optional

from icosa.models import Asset, PolyFormat, PolyResource, User
from ninja import File
from ninja.errors import HttpError
from ninja.files import UploadedFile

from django.core.files.storage import get_storage_class

default_storage = get_storage_class()()

ASSET_NOT_FOUND = HttpError(404, "Asset not found.")

IMAGE_REGEX = re.compile("(jpe?g|tiff?|png|webp|bmp)")

VALID_FORMAT_TYPES = [
    "tilt",
    "glb",
    "gltf",
    "bin",
    "obj",
    "mtl",
    "fbx",
    "fbm",
]

CONTENT_TYPE_MAP = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "tilt": "application/octet-stream",
    "glb": "model/gltf-binary",
    "gltf": "model/gltf+json",
    "bin": "application/octet-stream",
    "obj": "text/plain",
    "mtl": "text/plain",
    "fbx": "application/octet-stream",
    "fbm": "application/octet-stream",
}


def get_content_type(filename):
    extension = os.path.splitext(filename)[-1].replace(".", "")
    return CONTENT_TYPE_MAP.get(extension, None)


def upload_file_gcs(source_file, destination_blob_name):
    # stub to make the server run
    return True


@dataclass
class UploadedFormat:
    file: UploadedFile
    extension: str
    filetype: str
    mainfile: bool


def validate_file(
    file: UploadedFile, extension: str
) -> Optional[UploadedFormat]:
    # Need to check if the resource is a main file or helper file.
    # Ordered in most likely file types for 'performance'

    # TODO(safety): Do we fail to identify what the main file is if the zip
    # archive contains both (e.g.) a .tilt and a .fbx?

    if (
        extension not in VALID_FORMAT_TYPES
        and IMAGE_REGEX.match(extension) is None
    ):
        return None

    filetype = None
    mainfile = False

    if extension == "tilt":
        filetype = "TILT"
        mainfile = True

    # GLTF/GLB/BIN
    if extension == "glb":
        filetype = "GLTF2"
        mainfile = True
    if extension == "gltf":
        # TODO: need extra checks here to determine if GLTF 1 or 2.
        filetype = "GLTF2"
        mainfile = True
    if extension == "bin":
        filetype = "BIN"

    # OBJ
    if extension == "obj":
        filetype = "OBJ"
        mainfile = True
    if extension == "mtl":
        filetype = "MTL"

    # FBX
    if extension == "fbx":
        filetype = "FBX"
        mainfile = True
    if extension == "fbm":
        filetype = "FBM"

    # Images
    if IMAGE_REGEX.match(extension):
        filetype = "IMAGE"

    return UploadedFormat(
        file,
        extension,
        filetype,
        mainfile,
    )


def upload_asset(
    current_user: User,
    job_snowflake: int,
    files: List[UploadedFile] = File(...),
    thumbnail: UploadedFile = File(...),
):
    if len(files) == 0:
        raise HttpError(422, "No files provided.")

    # We need to see one of: tilt, glb, gltf, obj, fbx
    main_files = []
    sub_files = []
    name = ""

    processed_files = []
    for file in files:
        # Handle thumbnail included in the zip
        # How do we handle multiple thumbnails? Currently non-zip thumbnails
        # take priority
        if thumbnail is None and file.name.lower() in [
            "thumbnail.png",
            "thumbnail.jpg",
        ]:
            thumbnail = file
        elif file.name.endswith(".zip"):
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
                        processed_file = UploadedFile(
                            name=zip_info.filename,
                            file=io.BytesIO(content),
                        )
                        processed_files.append(processed_file)
                        if thumbnail is None and zip_info.filename.lower() in [
                            "thumbnail.png",
                            "thumbnail.jpg",
                        ]:
                            thumbnail = processed_file
        else:
            processed_files.append(file)

    for file in processed_files:
        splitnames = file.name.split(
            "."
        )  # TODO(james): better handled by the `os` module?
        extension = splitnames[-1].lower()
        upload_details = validate_file(file, extension)
        if upload_details is not None:
            if upload_details.mainfile is True:
                main_files.append(upload_details)
                name = splitnames[0]
            else:
                sub_files.append(upload_details)

    if name == "":
        raise HttpError(
            415, "Not supplied with one of tilt, glb, gltf, obj, fbx."
        )

    # begin upload process
    asset_token = secrets.token_urlsafe(8)
    resources = []

    # create an asset to attach files to
    asset_data = {
        "id": job_snowflake,
        "url": asset_token,
        "name": name,
        "formats": "",
        "owner": current_user,
        "curated": False,
    }

    asset = Asset.objects.create(**asset_data)
    first_format = None

    for mainfile in main_files:
        is_first_format = True
        # Main files determine folder
        base_path = f"{current_user.id}/{job_snowflake}/{mainfile.filetype}/"
        # model_path = base_path + f"model.{mainfile.extension}"
        # model_uploaded_url = upload_file_gcs(mainfile.file.file, model_path)
        format_data = {
            "format_type": mainfile.filetype,
            "asset": asset,
        }
        format = PolyFormat(**format_data)
        format.save()
        if is_first_format:
            first_format = format
            is_first_format = False
        resource_data = {
            "file": mainfile.file,
            "is_root": True,
            "asset": asset,
            "format": format,
            "contenttype": get_content_type(mainfile.file.name),
        }
        main_resource = PolyResource.objects.create(**resource_data)
        resources.append(main_resource)

        for subfile in sub_files:
            # Horrendous check for supposedly compatible subfiles. can
            # definitely be improved with parsing, but is it necessary?
            if (
                (
                    mainfile.filetype == "GLTF2"
                    and (
                        subfile.filetype == "BIN"
                        or subfile.filetype == "IMAGE"
                    )
                )
                or (
                    mainfile.filetype == "OBJ"
                    and (
                        subfile.filetype == "MTL"
                        or subfile.filetype == "IMAGE"
                    )
                )
                or (
                    mainfile.filetype == "FBX"
                    and (
                        subfile.filetype == "FBM"
                        or subfile.filetype == "IMAGE"
                    )
                )
            ):

                sub_resource_data = {
                    "file": subfile.file,
                    "format": format,
                    "is_root": False,
                    "asset": asset,
                    "contenttype": get_content_type(subfile.file.name),
                }
                PolyResource.objects.create(**sub_resource_data)

    if thumbnail and first_format:
        extension = thumbnail.name.split(".")[-1].lower()
        thumbnail_upload_details = validate_file(file, extension)
        if (
            thumbnail_upload_details is not None
            and thumbnail_upload_details.filetype == "IMAGE"
        ):
            asset.thumbnail = thumbnail_upload_details.file
            asset.thumbnail_contenttype = get_content_type(
                thumbnail_upload_details.file.name
            )
            asset.save()

    if len(resources) == 0:
        raise HttpError(500, "Unable to upload any files.")
    return asset


async def upload_thumbnail_background(
    current_user: User, thumbnail: UploadedFile, asset_id: int
):
    splitnames = thumbnail.name.split(".")
    extension = splitnames[-1].lower()
    if not IMAGE_REGEX.match(extension):
        raise HttpError(415, "Thumbnail must be png or jpg")

    base_path = f'{current_user["id"]}/{asset_id}/'
    thumbnail_path = f"{base_path}thumbnail.{extension}"
    thumbnail_uploaded_url = upload_file_gcs(thumbnail.file, thumbnail_path)

    # if thumbnail_uploaded_url:
    #     # Update database
    #     query = assets.update(None)
    #     query = query.where(assets.c.id == asset_id)
    #     query = query.values(thumbnail=thumbnail_uploaded_url)
    #     database.execute(query)
