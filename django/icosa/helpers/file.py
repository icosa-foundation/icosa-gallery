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
        # is_v2 = not isinstance(gltf["buffers"], dict)
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


def process_main_file(mainfile, sub_files, asset):
    is_first_format = True
    # Main files determine folder
    format_data = {
        "format_type": mainfile.filetype,
        "asset": asset,
    }
    format = PolyFormat.objects.create(**format_data)
    if is_first_format:
        is_first_format = False
    resource_data = {
        "file": mainfile.file,
        "is_root": True,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(mainfile.file.name),
    }
    PolyResource.objects.create(**resource_data)

    for subfile in sub_files:
        # Horrendous check for supposedly compatible subfiles. can
        # definitely be improved with parsing, but is it necessary?
        if (
            (
                mainfile.filetype == "GLTF2"
                and (subfile.filetype == "BIN" or subfile.filetype == "IMAGE")
            )
            or (
                mainfile.filetype == "OBJ"
                and (subfile.filetype == "MTL" or subfile.filetype == "IMAGE")
            )
            or (
                mainfile.filetype == "FBX"
                and (subfile.filetype == "FBM" or subfile.filetype == "IMAGE")
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


def add_thumbnail_to_asset(thumbnail, asset):
    extension = thumbnail.name.split(".")[-1].lower()
    thumbnail_upload_details = validate_file(thumbnail, extension)
    if (
        thumbnail_upload_details is not None
        and thumbnail_upload_details.filetype == "IMAGE"
    ):
        asset.thumbnail = thumbnail_upload_details.file
        asset.thumbnail_contenttype = get_content_type(
            thumbnail_upload_details.file.name
        )
        asset.save()


def get_role_id(f: UploadedFormat) -> Optional[int]:
    if f is None:
        return None
    filetype = f.filetype
    name = f.file.name.split(".")[0]
    if filetype == "OBJ":
        if name == "model-triangulated":
            return 24
        if name == "model":
            return 1
    if filetype == "GLTF2":
        return 12
    if filetype == "FBX":
        return 6
    if filetype == "TILT":
        return 2


def get_obj_non_triangulated(asset: Asset) -> Optional[PolyResource]:
    return asset.polyresource_set.filter(is_root=True, role=1).first()


def get_obj_triangulated(asset: Asset) -> Optional[PolyResource]:
    return asset.polyresource_set.filter(is_root=True, role=24).first()


def get_gltf(asset: Asset) -> Optional[PolyResource]:
    return asset.polyresource_set.filter(is_root=True, role=12).first()


def process_normally(asset: Asset, f: UploadedFormat):
    format_data = {
        "format_type": f.filetype,
        "asset": asset,
    }
    format = PolyFormat.objects.create(**format_data)
    resource_data = {
        "file": f.file,
        "format": format,
        "is_root": f.mainfile,
        "asset": asset,
        "contenttype": get_content_type(f.file.name),
        "role": get_role_id(f),
    }
    PolyResource.objects.create(**resource_data)


def process_mtl(asset: Asset, f: UploadedFormat):
    # Get or create both OBJ root resources that correspond to this MTL
    # along with the parent format.
    obj_non_triangulated = get_obj_non_triangulated(asset)
    obj_triangulated = get_obj_triangulated(asset)

    format_data = {
        "format_type": "OBJ",
        "asset": asset,
    }
    resource_data = {
        "file": None,
        "is_root": True,
        "asset": asset,
        "contenttype": "text/plain",
    }
    if obj_non_triangulated is None:
        format_non_triangulated = PolyFormat.objects.create(**format_data)
        obj_non_triangulated = PolyResource.objects.create(
            role=1, format=format_non_triangulated, **resource_data
        )
    else:
        format_non_triangulated = obj_non_triangulated.format
    if obj_triangulated is None:
        format_triangulated = PolyFormat.objects.create(**format_data)
        obj_triangulated = PolyResource.objects.create(
            role=24, format=format_triangulated, **resource_data
        )
    else:
        format_triangulated = obj_triangulated.format
    # Finally, create the duplicate MTL resources and assign them to the right
    # formats.
    resource_data = {
        "file": f.file,
        "is_root": False,
        "asset": asset,
        "contenttype": get_content_type(f.file.name),
    }
    PolyResource.objects.create(
        format=format_non_triangulated, **resource_data
    )
    PolyResource.objects.create(format=format_triangulated, **resource_data)


def process_bin(asset: Asset, f: UploadedFormat):
    # Get or create a GLTF root resource that correspond to this BIN along with
    # the parent format.
    gltf = get_gltf(asset)

    if gltf is None:
        format_data = {
            "format_type": "GLTF2",
            "asset": asset,
        }
        format = PolyFormat.objects.create(**format_data)
        resource_data = {
            "file": None,
            "is_root": True,
            "asset": asset,
            "contenttype": "application/gltf+json",
        }
        gltf = PolyResource.objects.create(
            role=12, format=format, **resource_data
        )
    else:
        format = gltf.format
    # Finally, create the duplicate BIN resource and assign it to the format.
    resource_data = {
        "file": f.file,
        "is_root": False,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(f.file.name),
    }
    PolyResource.objects.create(**resource_data)


def process_root(asset: Asset, f: UploadedFormat):
    root = asset.polyresource_set.filter(
        is_root=True, role=get_role_id(f), file=""
    ).first()
    if root is None:
        process_normally(asset, f)
    else:
        root.file = f.file
        root.save()


def upload_format(
    current_user: User,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    if files is None or len(files) > 1:
        raise HttpError(422, "Must upload exactly one file.")
    file = files[0]

    splitnames = file.name.split(
        "."
    )  # TODO(james): better handled by the `os` module?
    extension = splitnames[-1].lower()
    f = validate_file(file, extension)
    if f is None:
        raise HttpError(422, "Invalid file.")

    filetype = f.filetype

    if filetype == "MTL":
        process_mtl(asset, f)
    elif filetype == "BIN":
        process_bin(asset, f)
    elif filetype in ["OBJ", "GLTF2"]:
        process_root(asset, f)
    elif filetype == "IMAGE" and f.file.name == "thumbnail.png":
        asset.thumbnail = f.file
        asset.thumbnail_contenttype = get_content_type(f.file.name)
        asset.save()
    else:
        process_normally(asset, f)

    return asset


def upload_asset(
    current_user: User,
    job_snowflake: int,
    files: Optional[List[UploadedFile]] = File(None),
    thumbnail: UploadedFile = File(...),
):
    # We need to see one of: tilt, glb, gltf, obj, fbx
    main_files = []
    sub_files = []
    name = "Untitled Asset"

    unzipped_files = []
    if files is None:
        files = []
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
                        unzipped_files.append(processed_file)
                        if thumbnail is None and zip_info.filename.lower() in [
                            "thumbnail.png",
                            "thumbnail.jpg",
                        ]:
                            thumbnail = processed_file
        else:
            unzipped_files.append(file)

    for file in unzipped_files:
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

    # begin upload process
    asset_token = secrets.token_urlsafe(8)

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

    for mainfile in main_files:
        process_main_file(
            mainfile,
            sub_files,
            asset,
        )

    if thumbnail:
        add_thumbnail_to_asset(thumbnail, asset)

    return asset


def upload_thumbnail(
    thumbnail: UploadedFile,
    asset: Asset,
):
    splitnames = thumbnail.name.split(".")
    extension = splitnames[-1].lower()
    if not IMAGE_REGEX.match(extension):
        raise HttpError(415, "Thumbnail must be png or jpg")

    add_thumbnail_to_asset(thumbnail, asset)
