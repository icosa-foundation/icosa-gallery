import base64
import io
import os
import re
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import ijson
from django.conf import settings
from django.core.files.storage import get_storage_class
from django.core.files.uploadedfile import InMemoryUploadedFile
from icosa.helpers.format_roles import (
    BLOCKS_FORMAT,
    ORIGINAL_FBX_FORMAT,
    ORIGINAL_GLTF_FORMAT,
    ORIGINAL_OBJ_FORMAT,
    ORIGINAL_TRIANGULATED_OBJ_FORMAT,
    TILT_FORMAT,
)
from icosa.models import (
    ASSET_STATE_COMPLETE,
    Asset,
    AssetOwner,
    PolyFormat,
    PolyResource,
)
from ninja import File
from ninja.errors import HttpError
from ninja.files import UploadedFile
from PIL import Image

default_storage = get_storage_class()()

CONVERTER_EXE = "/node_modules/gltf-pipeline/bin/gltf-pipeline.js"


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
        if (value, event) == ("buffers", "map_key"):
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
            filetype = "GLTF"
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
    is_first_format = True
    # Main files determine folder
    format_type = mainfile.filetype
    file = mainfile.file
    name = mainfile.file.name

    # if this is a gltf1 and we have a converted file on disk, swap out the
    # uploaded file with the one we have on disk and change the format_type
    # to gltf2.
    if (
        format_type == "GLTF"
        and gltf_to_convert is not None
        and os.path.exists(gltf_to_convert)
    ):
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
    format = PolyFormat.objects.create(**format_data)
    if is_first_format:
        is_first_format = False

    resource_data = {
        "file": file,
        "is_root": True,
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(name),
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


def get_role_id_from_file(name: str, filetype: str) -> Optional[int]:
    filetype = filetype.upper()
    if filetype == "OBJ":
        if name == "model-triangulated":
            return ORIGINAL_TRIANGULATED_OBJ_FORMAT
        if name == "model":
            return ORIGINAL_OBJ_FORMAT
    if filetype in ["GLTF", "GLTF2"]:
        return ORIGINAL_GLTF_FORMAT
    if filetype == "FBX":
        return ORIGINAL_FBX_FORMAT
    if filetype == "TILT":
        return TILT_FORMAT
    if filetype == "BLOCKS":
        return BLOCKS_FORMAT
    return None


def get_role_id(f: UploadedFormat) -> Optional[int]:
    if f is None:
        return None
    filetype = f.filetype
    name = f.file.name.split(".")[0]
    return get_role_id_from_file(name, filetype)


def get_obj_non_triangulated(asset: Asset) -> Optional[PolyResource]:
    return asset.polyresource_set.filter(is_root=True, format__role=1).first()


def get_obj_triangulated(asset: Asset) -> Optional[PolyResource]:
    return asset.polyresource_set.filter(is_root=True, format__role=24).first()


def get_gltf(asset: Asset) -> Optional[PolyResource]:
    return asset.polyresource_set.filter(is_root=True, format__role=12).first()


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
    }
    resource_role = get_role_id(f)
    if resource_role is not None:
        format.role = resource_role
        format.save()

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
        format_non_triangulated = PolyFormat.objects.create(
            **format_data,
            role=1,
        )
        obj_non_triangulated = PolyResource.objects.create(
            format=format_non_triangulated, **resource_data
        )
    else:
        format_non_triangulated = obj_non_triangulated.format

    if obj_triangulated is None:
        format_triangulated = PolyFormat.objects.create(
            **format_data,
            role=24,
        )
        obj_triangulated = PolyResource.objects.create(
            format=format_triangulated, **resource_data
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
    PolyResource.objects.create(format=format_non_triangulated, **resource_data)
    PolyResource.objects.create(format=format_triangulated, **resource_data)


def process_bin(asset: Asset, f: UploadedFormat):
    # Get or create a GLTF root resource that correspond to this BIN along with
    # the parent format.
    gltf = get_gltf(asset)

    if gltf is None:
        if is_gltf2(f.file):
            format_type = "GLTF2"
        else:
            format_type = "GLTF"
        format_data = {
            "format_type": format_type,
            "asset": asset,
        }
        format = PolyFormat.objects.create(**format_data, role=12)
        resource_data = {
            "file": None,
            "is_root": True,
            "asset": asset,
            "contenttype": "application/gltf+json",
        }
        gltf = PolyResource.objects.create(format=format, **resource_data)
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
        is_root=True, format__role=get_role_id(f), file=""
    ).first()
    if root is None:
        process_normally(asset, f)
    else:
        root.file = f.file
        root.save()


def upload_format(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    if files is None or len(files) > 1:
        raise HttpError(422, "Must upload exactly one file.")
    file = files[0]

    splitnames = file.name.split(".")  # TODO(james): better handled by the `os` module?
    extension = splitnames[-1].lower()
    f = validate_file(file, extension)
    if f is None:
        raise HttpError(422, "Invalid file.")

    filetype = f.filetype
    existing_resource = asset.polyresource_set.filter(
        format__role=get_role_id(f), file__endswith=f.file.name
    ).first()

    if existing_resource is not None:
        existing_resource.file = f.file
        existing_resource.save()
    elif filetype == "MTL":
        process_mtl(asset, f)
    elif filetype == "BIN":
        process_bin(asset, f)
    elif filetype in ["OBJ", "GLTF2", "GLTF"]:
        process_root(asset, f)
    elif filetype == "IMAGE" and f.file.name == "thumbnail.png":
        asset.thumbnail = f.file
        asset.thumbnail_contenttype = get_content_type(f.file.name)
        # We save outside of this function too. Saving here is more explicit,
        # but might reduce perf.
        asset.save()
    else:
        process_normally(asset, f)

    return asset


def upload_asset(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    # We need to see one of: tilt, glb, gltf, obj, fbx
    main_files = []
    sub_files = []
    name = "Untitled Asset"
    thumbnail = None

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

    gltf_to_convert = None
    bin_for_conversion = None
    asset_dir = os.path.join("/tmp/", f"{asset.id}")
    for file in unzipped_files:
        splitext = os.path.splitext(file.name)
        extension = splitext[1].lower().replace(".", "")
        upload_details = validate_file(file, extension)
        if upload_details is not None:
            if upload_details.filetype in ["GLTF", "BIN"]:
                # Save the file for later conversion.
                file = upload_details.file
                Path(asset_dir).mkdir(parents=True, exist_ok=True)
                path = os.path.join(asset_dir, file.name)
                with open(path, "wb") as f_out:
                    for chunk in file.chunks():
                        f_out.write(chunk)
                    upload_details.file.seek(0)
                    if upload_details.filetype == "BIN":
                        bin_for_conversion = (
                            path,
                            file.name,
                        )
                    if upload_details.filetype == "GLTF":
                        gltf_to_convert = (
                            path,
                            file.name,
                        )

            if upload_details.mainfile is True:
                main_files.append(upload_details)
                name = splitext[0]
            else:
                sub_files.append(upload_details)

    converted_gltf_path = None
    if gltf_to_convert is not None and bin_for_conversion is not None:
        Path(os.path.join(asset_dir, "converted")).mkdir(parents=True, exist_ok=True)
        name, extension = os.path.splitext(gltf_to_convert[1])
        out_path = os.path.join(asset_dir, "converted", f"{name}.glb")
        data = Path(gltf_to_convert[0]).read_text()
        shader_dummy_path = os.path.join(settings.STATIC_ROOT, "shader_dummy")
        Path(gltf_to_convert[0]).write_text(
            data.replace("https://vr.google.com/shaders/w/", shader_dummy_path)
        )
        subprocess.run(
            [
                "node",
                CONVERTER_EXE,
                "-i",
                gltf_to_convert[0],
                "-o",
                out_path,
                "--keepUnusedElements",
                "--binary",
            ]
        )
        converted_gltf_path = out_path

    # Begin upload process.

    asset.name = name
    asset.save()

    for mainfile in main_files:
        process_main_file(
            mainfile,
            sub_files,
            asset,
            converted_gltf_path,
        )

    # Clean up temp files.
    # TODO(james) missing_ok might squash genuine errors where the file should
    # exist.
    if gltf_to_convert is not None:
        Path.unlink(gltf_to_convert[0], missing_ok=True)
    if bin_for_conversion is not None:
        Path.unlink(bin_for_conversion[0], missing_ok=True)
    if converted_gltf_path is not None:
        Path.unlink(converted_gltf_path, missing_ok=True)
    try:
        Path.rmdir(os.path.join(asset_dir, "converted"))
    except FileNotFoundError:
        pass
    try:
        Path.rmdir(os.path.join(asset_dir))
    except FileNotFoundError:
        pass

    if thumbnail:
        add_thumbnail_to_asset(thumbnail, asset)

    asset.state = ASSET_STATE_COMPLETE
    asset.save()
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
