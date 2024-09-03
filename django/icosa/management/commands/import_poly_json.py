import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from b2sdk.v2 import B2Api, InMemoryAccountInfo
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import (
    RESOURCE_ROLE_CHOICES,
    Asset,
    FormatComplexity,
    PolyFormat,
    PolyResource,
    Tag,
    User,
)

from django.conf import settings
from django.core.management.base import BaseCommand

POLY_JSON_DIR = "polygone_data"
ASSETS_JSON_DIR = f"{POLY_JSON_DIR}/assets"

EXTENSION_ROLE_MAP = {
    ".obj": 1,
    ".tilt": 2,
    ".fbx": 6,
    ".blocks": 7,
    ".usd": 8,
    ".html": 11,
    ".json": 15,
    ".glb": 36,
    ".gltf": 39,
}


def get_json_from_b2(dir):
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    b2_api.authorize_account(
        "production",
        settings.DJANGO_STORAGE_ACCESS_KEY,
        settings.DJANGO_STORAGE_SECRET_KEY,
    )
    bucket = b2_api.get_bucket_by_name("icosa-gallery")
    json_files = bucket.ls(
        folder_to_list="poly/*/data.json",
        latest_only=True,
        recursive=True,
        with_wildcard=True,
    )
    print("Downloading files...")
    for version, _ in json_files:
        # Strip the `/poly/` element off the path; we don't need that.
        path = os.path.join(dir, *version.file_name.split("/")[1:-1])
        path_with_file = os.path.join(path, "data.json")
        if os.path.exists(path_with_file):
            # Assuming the json data will never change once downloaded.
            print(version.file_name, "already exists; skipping.")
        else:
            print("Downloading", version.file_name, "...")
            download = version.download()
            # Create destination path only after download was successful.
            Path(path).mkdir(parents=True, exist_ok=True)
            download.save_to(path_with_file)
    print("Finished downloading files.")


def get_or_create_asset(dir, data):
    user, _ = User.objects.get_or_create(
        url=data["authorId"],
        defaults={
            "password": secrets.token_bytes(16),
            "displayname": data["authorName"],
        },
    )
    # user = None
    # A couple of background colours are expressed as malformed
    # rgb() values. Let's make them the default if so.
    background_color = data["presentationParams"].get("backgroundColor", None)
    if background_color is not None and len(background_color) > 7:
        background_color = "#000000"
    orienting_rotation = data["presentationParams"].get(
        "orientingRotation", None
    )
    orienting_rotation_x = orienting_rotation.get("x", None)
    orienting_rotation_y = orienting_rotation.get("y", None)
    orienting_rotation_z = orienting_rotation.get("z", None)
    orienting_rotation_w = orienting_rotation.get("w", None)

    return Asset.objects.get_or_create(
        url=dir,
        defaults=dict(
            name=data["name"],
            id=generate_snowflake(),
            imported=True,
            formats="",
            owner=user,
            description=data.get("description", None),
            visibility=data["visibility"],
            curated="curated" in data["tags"],
            polyid=dir,
            polydata=data,
            license=data["license"],
            create_time=datetime.fromisoformat(
                data["createTime"].replace("Z", "+00:00")
            ),
            update_time=datetime.fromisoformat(
                data["updateTime"].replace("Z", "+00:00")
            ),
            color_space=data["presentationParams"]["colorSpace"],
            background_color=background_color,
            orienting_rotation_x=orienting_rotation_x,
            orienting_rotation_y=orienting_rotation_y,
            orienting_rotation_z=orienting_rotation_z,
            orienting_rotation_w=orienting_rotation_w,
        ),
    )


def create_formats(directory, formats_json, asset):
    done_thumbnail = False
    for format_json in formats_json:
        format = PolyFormat.objects.create(
            asset=asset,
            format_type=format_json["formatType"],
        )
        if format_json.get("formatComplexity", None) is not None:
            format_complexity_json = format_json["formatComplexity"]
            format_complexity_data = {
                "triangle_count": format_complexity_json.get(
                    "triangleCount", None
                ),
                "lod_hint": format_complexity_json.get("lodHint", None),
                "format": format,
            }
            FormatComplexity.objects.create(**format_complexity_data)
        # Manually create thumbnails from our assumptions about the data.
        if not done_thumbnail:
            asset.thumbnail = f"poly/{directory}/thumbnail.png"
            asset.thumbnail_contenttype = "image/png"
            asset.save()
        done_thumbnail = True
        root_resource_json = format_json["root"]

        file_path = root_resource_json["relativePath"]
        extension = os.path.splitext(file_path)[-1].lower()
        role = EXTENSION_ROLE_MAP.get(extension)

        root_resource_data = {
            "file": f"poly/{directory}/{file_path}",
            "is_root": True,
            "format": format,
            "asset": asset,
            "contenttype": root_resource_json["contentType"],
            "role": role,
        }
        PolyResource.objects.create(**root_resource_data)

        if format_json.get("resources", None) is not None:
            for resource_json in format_json["resources"]:

                file_path = resource_json["relativePath"]
                extension = os.path.splitext(file_path)[-1].lower()
                role = EXTENSION_ROLE_MAP.get(extension)

                resource_data = {
                    "file": f"poly/{directory}/{file_path}",
                    "is_root": False,
                    "format": format,
                    "asset": asset,
                    "contenttype": resource_json["contentType"],
                    "role": role,
                }
                PolyResource.objects.create(**resource_data)


class Command(BaseCommand):

    help = "Imports poly json files from a local directory"

    def add_arguments(self, parser):
        parser.add_argument(
            "--download",
            action="store_true",
            help="Download data files from B2",
        )
        parser.add_argument(
            "--ids",
            nargs="*",
            help="Space-separated list of specific IDs to import.",
            default=[],
            type=str,
        )

    def handle(self, *args, **options):

        if options["download"]:
            get_json_from_b2(ASSETS_JSON_DIR)
            print(
                "Finished downloading. Run this command again without --download to process the files"
            )
            return

        if options["ids"]:
            directories = list(options["ids"])
        else:
            directories = os.listdir(ASSETS_JSON_DIR)

        # Loop through all directories in the poly json directory
        # For each directory, load the data.json file
        # Create a new Asset object with the data
        for directory in directories:
            if directory.startswith("."):
                continue
            full_path = os.path.join(ASSETS_JSON_DIR, directory, "data.json")
            try:
                with open(full_path) as f:
                    data = json.load(f)

                    formats = data["formats"]
                    new_formats = []
                    dup_types = {}

                    # Check json for duplicate gltf entries
                    for format in formats:
                        relative_path = format["root"]["relativePath"]
                        if dup_types.get(relative_path):
                            if relative_path != "model.gltf":
                                print(
                                    f"found duplicate for {directory} - {relative_path}"
                                )
                            continue
                        new_formats.append(format)
                        dup_types.update({relative_path: True})

                    try:
                        asset, asset_created = get_or_create_asset(
                            directory, data
                        )
                        if asset_created:
                            icosa_tags = []
                            for tag in data["tags"]:
                                obj, _ = Tag.objects.get_or_create(name=tag)
                                icosa_tags.append(obj)
                            asset.tags.set(icosa_tags)
                            create_formats(
                                directory,
                                new_formats,
                                asset,
                            )

                    except Exception as e:
                        _ = e
                        # from pprint import pprint
                        # print(e)
                        # pprint(data)
                        # continue
                        raise
            except FileNotFoundError as e:
                print(e)
                continue
