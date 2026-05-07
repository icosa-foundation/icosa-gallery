import io
import os
import subprocess
import zipfile
from pathlib import Path
from typing import List, Optional

from django.conf import settings
from django.utils import timezone
from icosa.api.exceptions import ZipException
from icosa.helpers.file import (
    MAX_UNZIP_BYTES,
    MAX_UNZIP_SECONDS,
    UploadedFormat,
    add_thumbnail_to_asset,
    get_content_type,
    validate_file,
)
from icosa.helpers.upload import TYPE_ROLE_MAP
from icosa.models import (
    ASSET_STATE_COMPLETE,
    Asset,
    Format,
    Resource,
)
from ninja import File
from ninja.files import UploadedFile

CONVERTER_EXE = "/node_modules/gltf-pipeline/bin/gltf-pipeline.js"

SUB_FILE_MAP = {
    "IMAGE": "GLB",
    "BIN": "GLTF",
}

VALID_WEB_FORMAT_TYPES = [
    "glb",
    "gltf",
    "bin",
    "jpeg",
    "jpg",
    "tif",
    "tiff",
    "png",
    "webp",
    "bmp",
    # new formats:
    "ksplat",
    "ply",
    "stl",
    "usdz",
    "vox",
    "sog",
    "spz",
    "splat",
]


def get_role(mainfile: UploadedFormat) -> str:
    type = mainfile.filetype
    if type in ["GLTF1", "GLTF2"]:
        role = "USER_SUPPLIED_GLTF"
    else:
        role = TYPE_ROLE_MAP.get(type, None)
    return role


def write_files_to_convert(in_file, asset_dir):
    file = in_file.file
    Path(asset_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(asset_dir, file.name)
    with open(path, "wb") as f_out:
        for chunk in file.chunks():
            f_out.write(chunk)
        in_file.file.seek(0)
        return (
            path,
            file.name,
        )


def convert_gltf(gltf_file, bin_file, asset_dir):
    if gltf_file is not None and bin_file is not None:
        Path(os.path.join(asset_dir, "converted")).mkdir(
            parents=True,
            exist_ok=True,
        )
        name, extension = os.path.splitext(gltf_file[1])
        out_path = os.path.join(
            asset_dir,
            "converted",
            f"{name}.glb",
        )
        data = Path(gltf_file[0]).read_text()
        shader_dummy_path = os.path.join(
            settings.STATIC_ROOT,
            "shader_dummy",
        )
        Path(gltf_file[0]).write_text(
            data.replace(
                "https://vr.google.com/shaders/w/",
                shader_dummy_path,
            )
        )
        subprocess.run(
            [
                "node",
                CONVERTER_EXE,
                "-i",
                gltf_file[0],
                "-o",
                out_path,
                "--keepUnusedElements",
                "--binary",
            ]
        )
        return out_path
    else:
        return None


def clean_up_conversion(gltf_file, bin_file, gltf_path, asset_dir):
    # Clean up temp files.
    # NOTE(james): missing_ok might squash genuine errors where the file should
    # exist.
    if gltf_file is not None:
        Path.unlink(gltf_file[0], missing_ok=True)
    if bin_file is not None:
        Path.unlink(bin_file[0], missing_ok=True)
    if gltf_path is not None:
        Path.unlink(gltf_path, missing_ok=True)
    try:
        Path.rmdir(os.path.join(asset_dir, "converted"))
    except FileNotFoundError:
        pass
    try:
        Path.rmdir(os.path.join(asset_dir))
    except FileNotFoundError:
        pass


def process_files(files: List[UploadedFile]) -> List[UploadedFile]:
    unzipped_files = []
    for file in files:
        # Note, the mime type should be checked in the form. This function
        # assumes the correct mime type for zip or glb TODO: or binary file.
        if not file.name.endswith(".zip"):
            unzipped_files.append(file)
            continue

        unzip_start = timezone.now()
        total_size_bytes = 0
        # Read the file as a ZIP file
        with zipfile.ZipFile(io.BytesIO(file.read())) as zip_file:
            # Iterate over each file in the ZIP
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
                    # Add the file to the list of unzipped files to process.
                    unzipped_files.append(processed_file)
    return unzipped_files


async def make_formats(mainfile, sub_files, asset, gltf_to_convert, role=None):
    # Main files determine folder
    format_type = mainfile.filetype
    name = mainfile.file.name
    file = mainfile.file
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
        "role": role,
    }
    format = await Format.objects.acreate(**format_data)

    root_resource_data = {
        "asset": asset,
        "format": format,
        "contenttype": get_content_type(name),
    }
    root_resource = await Resource.objects.acreate(**root_resource_data)
    await format.aadd_root_resource(root_resource)
    await format.asave()
    root_resource.file = file
    await root_resource.asave()

    for subfile in sub_files:
        sub_resource_data = {
            "file": subfile.file,
            "format": format,
            "asset": asset,
            "contenttype": get_content_type(subfile.file.name),
        }
        await Resource.objects.acreate(**sub_resource_data)


async def upload(
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    main_files = []
    # We need to see one of: glb or gltf, preferring glb.
    sub_files = {
        "GLB": [],  # All non-thumbnail images.
        "GLTF": [],  # All GLB's files plus BIN files.
    }
    asset_name = "Untitled Asset"

    if files is None:
        files = []
    try:
        unzipped_files = process_files(files)
    except ZipException as err:
        raise err

    thumbnail = None
    gltf_to_convert = bin_to_convert = None
    asset_dir = os.path.join("/tmp/", f"{asset.id}")

    for file in unzipped_files:
        splitext = os.path.splitext(file.name)
        ext = splitext[1].lower().replace(".", "")
        if ext not in VALID_WEB_FORMAT_TYPES:
            # validate_file will accept more than we want, so filter out types
            # we are not accepting from users here.
            continue

        valid_file = validate_file(file, ext)
        if valid_file is None:
            continue

        # TODO(james): This code will break in mysterious ways if we receive
        # more than one set of gltf/bin files and don't process the right bin
        # with the right gltf.
        # We will enable this once the upload process is stable.
        if False:
            if valid_file.filetype == "BIN" and bin_to_convert is None:
                bin_to_convert = write_files_to_convert(
                    valid_file,
                    asset_dir,
                )
            if valid_file.filetype == "GLTF1" and gltf_to_convert is None:
                gltf_to_convert = write_files_to_convert(
                    valid_file,
                    asset_dir,
                )

        if valid_file.mainfile is True:
            main_files.append(valid_file)
            asset_name = splitext[0]
        else:
            parent_resource_type = SUB_FILE_MAP[valid_file.filetype]
            sub_files[parent_resource_type].append(valid_file)

        if thumbnail is None:
            splitext = os.path.splitext(valid_file.file.name)
            if splitext[0].lower() == "thumbnail" and valid_file.filetype == "IMAGE":
                thumbnail = valid_file.file

    # Currently a no-op, will return None. See where we assign gltf_to_convert
    # and bin_to_convert.
    converted_gltf_path = convert_gltf(
        gltf_to_convert,
        bin_to_convert,
        asset_dir,
    )

    if not asset.name:
        asset.name = asset_name
    await asset.asave()

    for mainfile in main_files:
        type = mainfile.filetype
        if type.startswith("GLTF1"):
            sub_files_list = sub_files["GLTF"] + sub_files["GLB"]
        else:
            try:
                sub_files_list = sub_files[type]
            except KeyError:
                sub_files_list = []

        role = get_role(mainfile)
        await make_formats(
            mainfile,
            sub_files_list,
            asset,
            converted_gltf_path,
            role,
        )

    # Currently a no-op. # See where we assign gltf_to_convert and
    # bin_to_convert.
    clean_up_conversion(
        gltf_to_convert,
        bin_to_convert,
        converted_gltf_path,
        asset_dir,
    )

    if thumbnail is not None:
        await add_thumbnail_to_asset(thumbnail, asset)

    # Save here so all formats and resources are associated with the asset.
    # After this, we can mark each format as preferred.
    await asset.asave()

    await asset.assign_preferred_viewer_format()
    asset.state = ASSET_STATE_COMPLETE
    await asset.asave()

    return asset
