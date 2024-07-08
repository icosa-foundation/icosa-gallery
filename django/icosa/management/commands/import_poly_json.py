import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from b2sdk.v2 import B2Api, InMemoryAccountInfo
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import Asset, PolyFormat, PolyResource, Tag, User

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
        for dir in os.listdir(POLY_JSON_DIR):
            if dir.startswith("."):
                continue
            # print(directory)
            full_path = os.path.join(POLY_JSON_DIR, dir, "data.json")
            # print(full_path)
            try:
                with open(full_path) as f:
                    data = json.load(f)

                    user = User.objects.filter(url=data["authorId"]).first()

                    # A couple of background colours are expressed as malformed
                    # rgb() values. Let's make them the default if so.
                    background_color = data["presentationParams"].get(
                        "backgroundColor", None
                    )
                    if (
                        background_color is not None
                        and len(background_color) > 7
                    ):
                        background_color = "#000000"

                    try:
                        asset, asset_created = Asset.objects.get_or_create(
                            name=data["name"],
                            # TODO author=data["authorName"],
                            owner=user,
                            description=data.get("description", None),
                            formats="",
                            visibility=data["visibility"],
                            curated="curated" in data["tags"],
                            polyid=dir,
                            polydata=data,
                            thumbnail=None,
                            license=data["license"],
                            orienting_rotation=data["presentationParams"][
                                "orientingRotation"
                            ],
                            color_space=data["presentationParams"][
                                "colorSpace"
                            ],
                            background_color=background_color,
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
                        if asset_created:
                            icosa_tags = []
                            for tag in data["tags"]:
                                obj, _ = Tag.objects.get_or_create(name=tag)
                                icosa_tags.append(obj)
                            asset.tags.set(icosa_tags)
                            for format_json in data["formats"]:
                                format = PolyFormat.objects.create(
                                    asset=asset,
                                    format_type=format_json["formatType"],
                                )
                                root_resource_json = format_json["root"]
                                root_resource_data = {
                                    "file": f"poly/{dir}/{root_resource_json['relativePath']}",
                                    "is_root": True,
                                    "format": format,
                                }
                                PolyResource.objects.create(
                                    **root_resource_data
                                )
                                if (
                                    format_json.get("resources", None)
                                    is not None
                                ):
                                    for resource_json in format_json[
                                        "resources"
                                    ]:
                                        resource_data = {
                                            "file": f"poly/{dir}/{resource_json['relativePath']}",
                                            "is_root": False,
                                            "format": format,
                                        }
                                        PolyResource.objects.create(
                                            **resource_data
                                        )

                    except Exception as e:
                        raise
                        from pprint import pprint

                        print(e)
                        pprint(data)
            except FileNotFoundError as e:
                print(e)
                continue
