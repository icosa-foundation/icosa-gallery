import base64
import io
import os
import re
import time
from collections.abc import Buffer
from dataclasses import dataclass
from typing import List, Optional

import ijson
import magic
from django.core.files.uploadedfile import InMemoryUploadedFile
from icosa.helpers.logger import icosa_log
from icosa.models import (
    ASSET_STATE_UPLOADING,
    VALID_THUMBNAIL_MIME_TYPES,
    Asset,
    Format,
    Resource,
)
from ninja import File
from ninja.errors import HttpError
from ninja.files import UploadedFile
from PIL import Image

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
    "blocks",
    "stl",
    "usdz",
    "vox",
    "ply",
    "spz",
    "splat",
    "ksplat"
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
    "blocks": "application/octet-stream",
}


MAX_UNZIP_BYTES = 524288000  # 500MB

MAX_UNZIP_SECONDS = 120


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


def is_gltf2(file) -> bool:
    parser = ijson.parse(file, multiple_values=True)
    for prefix, event, value in parser:
        if (prefix, event) == ("buffers", "map_key"):
            # We are mapping a dictionary at the key `buffers`, which means
            # this is gltf1.
            return False
    return True


def validate_file(file: UploadedFile, extension: str) -> Optional[UploadedFormat]:
    # Need to check if the resource is a main file or helper file.
    # Ordered in most likely file types for 'performance'

    # TODO(safety): Do we fail to identify what the main file is if the zip
    # archive contains both (e.g.) a .tilt and a .fbx?

    if extension not in VALID_FORMAT_TYPES and IMAGE_REGEX.match(extension) is None:
        return None

    filetype = None
    mainfile = False

    if extension == "tilt":
        filetype = "TILT"
        mainfile = True

    if extension == "blocks":
        filetype = "BLOCKS"
        mainfile = True

    # GLTF/GLB/BIN
    if extension == "glb":
        filetype = "GLTF2"
        mainfile = True
    if extension == "gltf":
        if is_gltf2(file.file):
            filetype = "GLTF2"
        else:
            filetype = "GLTF1"
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


def process_main_file(mainfile, sub_files, asset, gltf_to_convert):
    # Main files determine folder
    format_type = mainfile.filetype
    file = mainfile.file
    name = mainfile.file.name

    # if this is a gltf1 and we have a converted file on disk, swap out the
    # uploaded file with the one we have on disk and change the format_type
    # to gltf2.
    if format_type == "GLTF1" and gltf_to_convert is not None and os.path.exists(gltf_to_convert):
        format_type = "GLB"
        name = f"{os.path.splitext(name)[0]}.glb"
        with open(gltf_to_convert, "rb") as f:
            file = UploadedFile(
                name=name,
                file=io.BytesIO(f.read()),
            )

    format_data = {
        "format_type": format_type,
        "asset": asset,
    }
    format = Format.objects.create(**format_data)

    resource_data = {
        "file": file,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(name),
    }
    root_resource = Resource.objects.create(**resource_data)
    format.add_root_resource(root_resource)

    for subfile in sub_files:
        # Horrendous check for supposedly compatible subfiles. can
        # definitely be improved with parsing, but is it necessary?
        if (
            (mainfile.filetype == "GLTF2" and (subfile.filetype == "BIN" or subfile.filetype == "IMAGE"))
            or (mainfile.filetype == "OBJ" and (subfile.filetype == "MTL" or subfile.filetype == "IMAGE"))
            or (mainfile.filetype == "FBX" and (subfile.filetype == "FBM" or subfile.filetype == "IMAGE"))
        ):
            sub_resource_data = {
                "file": subfile.file,
                "format": format,
                "asset": asset,
                "contenttype": get_content_type(subfile.file.name),
            }
            Resource.objects.create(**sub_resource_data)


def add_thumbnail_to_asset(thumbnail, asset):
    extension = thumbnail.name.split(".")[-1].lower()
    thumbnail_upload_details = validate_file(thumbnail, extension)
    if thumbnail_upload_details is not None and thumbnail_upload_details.filetype == "IMAGE":
        asset.thumbnail = thumbnail_upload_details.file
        asset.thumbnail_contenttype = get_content_type(thumbnail_upload_details.file.name)
        asset.save()


def get_blocks_role_id_from_file(name: str, filetype: str) -> Optional[int]:
    filetype = filetype.upper()
    # TODO(james): If the OBJ is not from blocks, the default from other apps
    # will probably be triangulated OBJ.
    if filetype == "OBJ":
        if name == "model-triangulated":
            return "ORIGINAL_TRIANGULATED_OBJ_FORMAT"
        if name == "model":
            return "ORIGINAL_OBJ_FORMAT"
    # For tilt, have a new role, TILT_NATIVE_GLTF, which behaves like
    # UPDATED_GLTF currently.
    if filetype in ["GLTF1", "GLTF2"]:
        return "ORIGINAL_GLTF_FORMAT"
    if filetype == "FBX":
        return "ORIGINAL_FBX_FORMAT"
    if filetype == "TILT":
        return "TILT_FORMAT"
    if filetype == "BLOCKS":
        return "BLOCKS_FORMAT"
    return None


def get_blocks_role_id(f: UploadedFormat) -> Optional[int]:
    if f is None:
        return None
    filetype = f.filetype
    name = f.file.name.split(".")[0]
    return get_blocks_role_id_from_file(name, filetype)


def get_obj_non_triangulated(asset: Asset) -> Optional[Resource]:
    resource = None
    format = asset.format_set.filter(
        root_resource__isnull=False,
        role="OBJ_NGON",
    ).last()
    if format:
        resource = format.root_resource
    return resource


def get_obj_triangulated(asset: Asset) -> Optional[Resource]:
    resource = None
    format = asset.format_set.filter(
        root_resource__isnull=False,
        format_type="OBJ",
    ).last()
    if format:
        resource = format.root_resource
    return resource


def get_gltf(asset: Asset) -> Optional[Resource]:
    resource = None
    format = asset.format_set.filter(
        root_resource__isnull=False,
        format_type__in=["GLTF1", "GLTF2"],
    ).last()
    if format:
        resource = format.root_resource
    return resource


def process_normally(asset: Asset, f: UploadedFormat):
    format_data = {
        "format_type": f.filetype,
        "asset": asset,
    }
    format = Format.objects.create(**format_data)

    if f.mainfile:
        root_resource_data = {
            "file": f.file,
            "asset": asset,
            "format": format,
            "contenttype": get_content_type(f.file.name),
        }
        root_resource = Resource.objects.create(**root_resource_data)
        format.add_root_resource(root_resource)
    else:
        resource_data = {
            "file": f.file,
            "format": format,
            "asset": asset,
            "contenttype": get_content_type(f.file.name),
        }
        Resource.objects.create(**resource_data)

    resource_role = get_blocks_role_id(f)
    if resource_role is not None:
        format.role = resource_role
        format.save()


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
        "asset": asset,
        "contenttype": "text/plain",
    }
    if obj_non_triangulated is None:
        format_non_triangulated = Format.objects.create(
            **format_data,
            role="ORIGINAL_OBJ_FORMAT",
        )
        obj_non_triangulated = Resource.objects.create(**resource_data)
        format_non_triangulated.add_root_resource(obj_non_triangulated)
        format_non_triangulated.save()
    else:
        format_non_triangulated = Format.objects.filter(
            root_resource=obj_non_triangulated,
        ).first()

    if obj_triangulated is None:
        format_triangulated = Format.objects.create(
            **format_data,
            role="ORIGINAL_TRIANGULATED_OBJ_FORMAT",
        )
        obj_triangulated = Resource.objects.create(**resource_data)
        format_triangulated.add_root_resource(obj_triangulated)
        format_triangulated.save()
    else:
        format_triangulated = Format.objects.filter(
            root_resource=obj_triangulated,
        ).first()
    # Finally, create the duplicate MTL resources and assign them to the right
    # formats.
    resource_data = {
        "file": f.file,
        "asset": asset,
        "contenttype": get_content_type(f.file.name),
    }
    Resource.objects.create(format=format_non_triangulated, **resource_data)
    Resource.objects.create(format=format_triangulated, **resource_data)


def process_bin(asset: Asset, f: UploadedFormat):
    # Get or create a GLTF root resource that corresponds to this BIN along
    # with the parent format.
    gltf = get_gltf(asset)

    if gltf is None:
        if is_gltf2(f.file):
            format_type = "GLTF2"
        else:
            format_type = "GLTF1"
        format_data = {
            "format_type": format_type,
            "asset": asset,
        }
        format = Format.objects.create(
            **format_data,
            role="ORIGINAL_GLTF_FORMAT",  # TODO, I don't think we need to assign this any more.
        )
        resource_data = {
            "file": None,
            "asset": asset,
            "format": format,
            "contenttype": "application/gltf+json",
        }
        gltf = Resource.objects.create(**resource_data)
        format.add_root_resource(gltf)
        format.save()
    else:
        format = Format.objects.filter(root_resource=gltf).first()
    # Finally, create the duplicate BIN resource and assign it to the format.
    resource_data = {
        "file": f.file,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(f.file.name),
    }
    Resource.objects.create(**resource_data)


def process_root(asset: Asset, f: UploadedFormat):
    root = None
    format = asset.format_set.filter(
        root_resource__isnull=False,
        role=get_blocks_role_id(f),
    ).first()
    if format and format.root_resource.file == "":
        root = format.root_resource

    if root is None:
        process_normally(asset, f)
    else:
        root.file = f.file
        root.save()


def upload_blocks_format(
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    asset.state = ASSET_STATE_UPLOADING
    asset.save()
    if files is None or len(files) > 1:
        raise HttpError(422, "Must upload exactly one file.")
    file = files[0]

    splitnames = file.name.split(".")  # TODO(james): better handled by the `os` module?
    extension = splitnames[-1].lower()
    f = validate_file(file, extension)
    if f is None:
        raise HttpError(422, "Invalid file.")

    filetype = f.filetype
    existing_resource = asset.resource_set.filter(
        format__role=get_blocks_role_id(f), file__endswith=f.file.name
    ).first()

    start = time.time()  # Logging

    if existing_resource is not None:
        existing_resource.file = f.file
        existing_resource.save()
    elif filetype == "MTL":
        process_mtl(asset, f)
    elif filetype == "BIN":
        process_bin(asset, f)
    elif filetype in ["OBJ", "GLTF2", "GLTF1"]:
        process_root(asset, f)
    elif filetype == "IMAGE" and f.file.name == "thumbnail.png":
        magic_bytes = next(f.file.chunks(chunk_size=2048))
        f.file.seek(0)
        if validate_mime(magic_bytes, VALID_THUMBNAIL_MIME_TYPES):
            asset.thumbnail = f.file
            asset.thumbnail_contenttype = get_content_type(f.file.name)
            # We save outside of this function too. Saving here is more explicit,
            # but might reduce perf.
            asset.save()
        else:
            raise HttpError(400, "Thumbnail must be png or jpg.")
    else:
        process_normally(asset, f)

    end = time.time()  # Logging
    icosa_log(f"Finished uploading {file} for asset {asset.url} in {end - start} seconds")  # Logging

    return asset


def b64_to_img(b64_image: str) -> InMemoryUploadedFile:
    _, imgstr = b64_image.split(";base64,")
    # Decode base64 data to a buffer.
    image_bytes_in = io.BytesIO(base64.b64decode(imgstr))

    # Remove alpha channel and save into a fresh buffer as jpg.
    pil_image = Image.open(image_bytes_in)
    jpg_image = pil_image.convert("RGB")
    image_bytes_out = io.BytesIO()
    jpg_image.save(image_bytes_out, format="JPEG", quality=85)

    # Construct a file object Django can deal with.
    return InMemoryUploadedFile(
        image_bytes_out,
        None,
        "preview_image.jpg",
        "image/jpeg",
        image_bytes_out.getbuffer().nbytes,
        None,
    )


def validate_mime(buffer: Buffer, valid_types: List[str]):
    mime_type = magic.from_buffer(buffer, mime=True)
    return mime_type in valid_types
