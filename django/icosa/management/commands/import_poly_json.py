import json
import os
import secrets
from datetime import datetime

from icosa.helpers.snowflake import generate_snowflake
from icosa.models import Asset, Tag, User

from django.core.management.base import BaseCommand


class Command(BaseCommand):

    help = "Imports poly json files from a local directory"

    def handle(self, *args, **options):

        POLY_JSON_DIR = "polygone_data/assets"

        # Loop through all directories in the poly json directory
        # For each directory, load the data.json file
        # Create a new Asset object with the data
        for directory in os.listdir(POLY_JSON_DIR):
            if directory.startswith("."):
                continue
            # print(directory)
            full_path = os.path.join(POLY_JSON_DIR, directory, "data.json")
            # print(full_path)
            with open(full_path) as f:
                data = json.load(f)

                user = User.objects.filter(url=data["authorId"]).first()

                # A couple of background colours are expressed as malformed
                # rgb() values. Let's make them the default if so.
                background_color = data["presentationParams"].get(
                    "backgroundColor", None
                )
                if background_color is not None and len(background_color) > 7:
                    background_color = "#000000"

                try:
                    asset, asset_created = Asset.objects.get_or_create(
                        name=data["name"],
                        # TODO author=data["authorName"],
                        owner=user,
                        description=data.get("description", None),
                        formats=data["formats"],
                        visibility=data["visibility"],
                        curated="curated" in data["tags"],
                        polyid=directory,
                        polydata=data,
                        thumbnail=None,
                        license=data["license"],
                        # tags=data["tags"],
                        orienting_rotation=data["presentationParams"][
                            "orientingRotation"
                        ],
                        color_space=data["presentationParams"]["colorSpace"],
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
                            "url": secrets.token_urlsafe(8),
                        },
                    )
                    if asset_created:
                        icosa_tags = []
                        for tag in data["tags"]:
                            obj, _ = Tag.objects.get_or_create(name=tag)
                            icosa_tags.append(obj)
                        asset.tags.set(icosa_tags)
                    else:
                        print("got it already")
                except Exception as e:
                    from pprint import pprint

                    print(e)
                    pprint(data)
                # Loop through all the files in the directory; for each file,
                # create a new File object and associate it with the Asset.
                # Currently, the sparse checkout does not include these extra
                # files.
                # for file in os.listdir(directory):
                #     file = File.objects.create(
                #         asset=asset,
                #         filename=file,
                #         path=directory + "/" + file,
                #     )
                #     file.save()
