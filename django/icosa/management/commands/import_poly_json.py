import json
import os
from datetime import datetime

from icosa.models import Asset, User

from django.core.management.base import BaseCommand, CommandError


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
            print(directory)
            full_path = os.path.join(POLY_JSON_DIR, directory, "data.json")
            print(full_path)
            with open(full_path) as f:
                data = json.load(f)

                user = User.objects.filter(url=data["authorId"]).first()

                asset = Asset(
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
                    tags=data["tags"],
                    orienting_rotation=data["presentationParams"][
                        "orientingRotation"
                    ],
                    color_space=data["presentationParams"]["colorSpace"],
                    background_color=data["presentationParams"].get(
                        "backgroundColor", None
                    ),
                    create_time=datetime.fromisoformat(
                        data["createTime"].replace("Z", "+00:00")
                    ),
                    update_time=datetime.fromisoformat(
                        data["updateTime"].replace("Z", "+00:00")
                    ),
                )
                print(asset)
                # asset.save()
                # Loop through all the files in the directory
                # For each file, create a new File object and associate it with the Asset
                # for file in os.listdir(directory):
                #     file = File.objects.create(
                #         asset=asset,
                #         filename=file,
                #         path=directory + "/" + file,
                #     )
                #     file.save()
