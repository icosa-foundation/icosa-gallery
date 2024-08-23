import json
import secrets
from datetime import datetime

from icosa.helpers.file import get_content_type
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

from django.core.management.base import BaseCommand

RESOURCE_ROLE_MAP = {x[1]: x[0] for x in RESOURCE_ROLE_CHOICES}


def get_or_create_asset(directory, data):
    user, _ = User.objects.get_or_create(
        url=data["authorId"],
        defaults={
            "password": secrets.token_bytes(16),
            "displayname": data["authorName"],
        },
    )
    presentation_params = data.get("presentationParams", {})
    # A couple of background colours are expressed as malformed
    # rgb() values. Let's make them the default if so.
    background_color = presentation_params.get("backgroundColor", None)
    if background_color is not None and len(background_color) > 7:
        background_color = "#000000"
    orienting_rotation = presentation_params.get("orientingRotation", {})
    orienting_rotation_x = orienting_rotation.get("x", None)
    orienting_rotation_y = orienting_rotation.get("y", None)
    orienting_rotation_z = orienting_rotation.get("z", None)
    orienting_rotation_w = orienting_rotation.get("w", None)

    return Asset.objects.get_or_create(
        url=directory,
        defaults=dict(
            name=data["name"],
            id=generate_snowflake(),
            imported=True,
            formats="",
            owner=user,
            description=data.get("description", None),
            visibility=data["visibility"],
            curated="curated" in data["tags"],
            polyid=directory,
            polydata=data,
            license=data.get("licence", ""),
            create_time=datetime.fromisoformat(
                data["createTime"].replace("Z", "+00:00")
            ),
            update_time=datetime.fromisoformat(
                data["updateTime"].replace("Z", "+00:00")
            ),
            color_space=presentation_params.get("colorSpace", "LINEAR"),
            background_color=background_color,
            orienting_rotation_x=orienting_rotation_x,
            orienting_rotation_y=orienting_rotation_y,
            orienting_rotation_z=orienting_rotation_z,
            orienting_rotation_w=orienting_rotation_w,
        ),
    )


def create_formats(formats_json, asset):
    # done_thumbnail = False
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
        # TODO(james): we need to either download the thumbnail from
        # archive.org and store it ourselves or add another field for external
        # thumbnail which references the external image.

        # Manually create thumbnails from our assumptions about the data.
        # if not done_thumbnail:
        #     asset.thumbnail = f"poly/{directory}/thumbnail.png"
        #     asset.thumbnail_contenttype = "image/png"
        #     asset.save()
        # done_thumbnail = True
        root_resource_json = format_json["root"]
        url = root_resource_json["url"]
        root_resource_data = {
            "external_url": f"https://web.archive.org/web/{url}",
            "is_root": True,
            "format": format,
            "asset": asset,
            "contenttype": get_content_type(url),
            "role": RESOURCE_ROLE_MAP[root_resource_json["role"]],
        }
        PolyResource.objects.create(**root_resource_data)
        if format_json.get("resources", None) is not None:
            for resource_json in format_json["resources"]:
                url = resource_json["url"]
                resource_data = {
                    "external_url": f"https://web.archive.org/web/{url}",
                    "is_root": False,
                    "format": format,
                    "asset": asset,
                    "contenttype": get_content_type(url),
                }
                PolyResource.objects.create(**resource_data)
            # If a format has many files associated with it (i.e. it has a
            # `resources` key), then we want to grab the archive url if we have
            # it so we can provide this in the download options for the user.
            if format_json.get("archive", None):
                format.archive_url = format_json["archive"]["url"]
                format.save()


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

        # Loop through all directories in the poly json directory
        # For each directory, load the data.json file
        # Create a new Asset object with the data

        with open("./all_data.jsonl", "r") as json_file:
            json_list = list(json_file)

            for json_str in json_list:
                data = json.loads(json_str)
                asset_id = data["assetId"]
                print(f"Importing {asset_id}")

                try:
                    asset, asset_created = get_or_create_asset(asset_id, data)
                    if asset_created:
                        icosa_tags = []
                        for tag in data["tags"]:
                            obj, _ = Tag.objects.get_or_create(name=tag)
                            icosa_tags.append(obj)
                        asset.tags.set(icosa_tags)
                        create_formats(
                            data["formats"],
                            asset,
                        )
                    else:
                        print(f"Skipping {asset_id}")

                except Exception as e:
                    _ = e
                    # from pprint import pprint
                    # print(e)
                    # pprint(data)
                    # continue
                    raise
