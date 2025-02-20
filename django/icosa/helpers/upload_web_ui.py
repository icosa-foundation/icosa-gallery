import io
import os
import subprocess
import zipfile
from pathlib import Path
from typing import List, Optional

from django.conf import settings
from icosa.helpers.file import process_main_file, validate_file
from icosa.models import (
    ASSET_STATE_COMPLETE,
    Asset,
    AssetOwner,
)
from ninja import File
from ninja.files import UploadedFile

CONVERTER_EXE = "/node_modules/gltf-pipeline/bin/gltf-pipeline.js"


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


def upload(
    current_user: AssetOwner,
    asset: Asset,
    files: Optional[List[UploadedFile]] = File(None),
):
    # We need to see one of: glb or gltf, preferring glb.
    main_files = []
    sub_files = []
    name = "Untitled Asset"

    unzipped_files = []
    if files is None:
        files = []
    for file in files:
        if file.name.endswith(".zip"):
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
        else:
            unzipped_files.append(file)

    gltf_to_convert = bin_for_conversion = None
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

            # TODO(james): this is wrong; each main file needs its own unique
            # set of subfiles.
            if upload_details.mainfile is True:
                main_files.append(upload_details)
                name = splitext[0]
            else:
                sub_files.append(upload_details)

    converted_gltf_path = convert_gltf(gltf_to_convert)

    asset.name = name
    asset.save()

    for mainfile in main_files:
        process_main_file(
            mainfile,
            sub_files,
            asset,
            converted_gltf_path,
        )

    clean_up_conversion(
        gltf_to_convert,
        bin_for_conversion,
        converted_gltf_path,
        asset_dir,
    )

    asset.state = ASSET_STATE_COMPLETE
    asset.save()
    return asset
