import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from b2sdk.v2 import B2Api, InMemoryAccountInfo
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import (
    Asset,
    FormatComplexity,
    OrientingRotation,
    PolyFormat,
    PolyResource,
    PresentationParams,
    Tag,
    User,
)

from django.conf import settings
from django.core.management.base import BaseCommand

POLY_JSON_DIR = "polygone_data/assets"


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
    orienting_rotation = OrientingRotation.objects.create(
        **data["presentationParams"]["orientingRotation"]
    )
    presentation_params = PresentationParams.objects.create(
        color_space=data["presentationParams"]["colorSpace"],
        background_color=background_color,
        orienting_rotation=orienting_rotation,
    )
    return Asset.objects.get_or_create(
        name=data["name"],
        owner=user,
        description=data.get("description", None),
        formats="",
        visibility=data["visibility"],
        curated="curated" in data["tags"],
        polyid=dir,
        polydata=data,
        thumbnail=None,
        license=data["license"],
        presentation_params=presentation_params,
        create_time=datetime.fromisoformat(
            data["createTime"].replace("Z", "+00:00")
        ),
        update_time=datetime.fromisoformat(
            data["updateTime"].replace("Z", "+00:00")
        ),
        defaults={
            "id": generate_snowflake(),
            "imported": True,
            "url": dir,
        },
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
            thumbnail_resource_data = {
                "file": f"poly/{directory}/thumbnail.png",
                "is_root": False,
                "is_thumbnail": True,
                "format": format,
                "asset": asset,
                "contenttype": "image/png",
            }
            PolyResource.objects.create(**thumbnail_resource_data)
        done_thumbnail = True
        root_resource_json = format_json["root"]
        root_resource_data = {
            "file": f"poly/{directory}/{root_resource_json['relativePath']}",
            "is_root": True,
            "format": format,
            "asset": asset,
            "contenttype": root_resource_json["contentType"],
        }
        PolyResource.objects.create(**root_resource_data)
        if format_json.get("resources", None) is not None:
            for resource_json in format_json["resources"]:
                resource_data = {
                    "file": f"poly/{directory}/{resource_json['relativePath']}",
                    "is_root": False,
                    "format": format,
                    "asset": asset,
                    "contenttype": resource_json["contentType"],
                }
                PolyResource.objects.create(**resource_data)


class Command(BaseCommand):

    help = "Imports poly json files from a local directory"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-import",
            action="store_true",
            help="Only download the json files, do not process them",
        )
        parser.add_argument(
            "--skip-download",
            action="store_true",
            help="Process existing json files without downloading any",
        )

    def handle(self, *args, **options):

        if options["skip_import"] and options["skip_download"]:
            print(
                "Nothing to do when --skip-import and --skip-download are used together."
            )
            return
        if not options["skip_download"]:
            get_json_from_b2(POLY_JSON_DIR)
        if options["skip_import"]:
            return

        # Loop through all directories in the poly json directory
        # For each directory, load the data.json file
        # Create a new Asset object with the data
        for directory in os.listdir(POLY_JSON_DIR):
            if directory.startswith("."):
                continue
            full_path = os.path.join(POLY_JSON_DIR, directory, "data.json")
            try:
                with open(full_path) as f:
                    data = json.load(f)
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
                            create_formats(directory, data["formats"], asset)

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
