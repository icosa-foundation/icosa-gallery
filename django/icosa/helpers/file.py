import io
import re
import secrets
import zipfile
from dataclasses import dataclass
from typing import List, Optional

from icosa.helpers.snowflake import generate_snowflake
from icosa.models import Asset, IcosaFormat, User
from ninja import File
from ninja.errors import HttpError
from ninja.files import UploadedFile

from django.core.files.storage import get_storage_class

default_storage = get_storage_class()()

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

ASSET_NOT_FOUND = HttpError(404, "Asset not found.")


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
    formats = []

    # create an asset to attach files to
    asset_data = {
        "id": job_snowflake,
        "url": asset_token,
        "name": name,
        "formats": "",
        "owner": current_user,
    }

    asset = Asset(**asset_data)
    asset.save()

    for mainfile in main_files:
        # Main files determine folder
        base_path = f"{current_user.id}/{job_snowflake}/{mainfile.filetype}/"
        # model_path = base_path + f"model.{mainfile.extension}"
        # model_uploaded_url = upload_file_gcs(mainfile.file.file, model_path)
        mainfile_snowflake = generate_snowflake()
        format_data = {
            "id": mainfile_snowflake,
            "file": mainfile.file,
            "format": mainfile.filetype,
            "asset": asset,
            "url": "",
            "is_mainfile": True,
        }
        main_format = IcosaFormat(**format_data)
        main_format.save()
        formats.append(main_format)

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

                subfile_snowflake = generate_snowflake()
                sub_format_data = {
                    "id": subfile_snowflake,
                    "asset": asset,
                    "file": subfile.file,
                    "format": subfile.filetype,
                    "url": "",
                }
                sub_format = IcosaFormat(**sub_format_data)
                sub_format.save()
                main_format.subfiles.add(sub_format)

    if thumbnail:
        extension = thumbnail.name.split(".")[-1].lower()
        thumbnail_upload_details = validate_file(file, extension)
        if (
            thumbnail_upload_details is not None
            and thumbnail_upload_details.filetype == "IMAGE"
        ):
            asset.thumbnail = thumbnail_upload_details.file
            asset.save()

    if len(formats) == 0:
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
