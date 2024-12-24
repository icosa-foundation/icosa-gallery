import json
import secrets
from datetime import datetime

from icosa.helpers.file import get_content_type
from icosa.helpers.format_roles import EXTENSION_ROLE_MAP
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import (
    ASSET_STATE_COMPLETE,
    CATEGORY_CHOICES,
    FORMAT_ROLE_CHOICES,
    Asset,
    PolyFormat,
    PolyResource,
    Tag,
    User,
)

from django.core.management.base import BaseCommand

IMPORT_SOURCE = "internet_archive"
FORMAT_ROLE_MAP = {x[1]: x[0] for x in FORMAT_ROLE_CHOICES}
VALID_TYPES = [x.replace(".", "").upper() for x in EXTENSION_ROLE_MAP.keys()]
CATEGORY_REVERSE_MAP = dict([(x[1], x[0]) for x in CATEGORY_CHOICES])


def get_or_create_asset(directory, data):
    user, _ = User.objects.get_or_create(
        url=data["authorId"],
        defaults={
            "password": secrets.token_bytes(16),
            "displayname": data["authorName"],
            "imported": True,
        },
    )
    presentation_params = data.get("presentationParams", {})
    # A couple of background colours are expressed as malformed
    # rgb() values. Let's make them the default if so.
    background_color = presentation_params.get("backgroundColor", None)
    if background_color is not None and len(background_color) > 7:
        presentation_params["backgroundColor"] = "#000000"

    license = data.get("licence", "")

    if license in ["CREATIVE_COMMONS_BY", "CREATIVE_COMMONS_BY_ND"]:
        license = f"{license}_3_0"

    return Asset.objects.get_or_create(
        url=directory,
        defaults=dict(
            state=ASSET_STATE_COMPLETE,
            name=data["name"],
            id=generate_snowflake(),
            imported_from=IMPORT_SOURCE,
            formats="",
            owner=user,
            description=data.get("description", None),
            visibility=data["visibility"],
            curated=data["curated"],
            polyid=directory,
            polydata=data,
            license=license,
            create_time=datetime.fromisoformat(
                data["createTime"].replace("Z", "+00:00")
            ),
            update_time=datetime.fromisoformat(
                data["updateTime"].replace("Z", "+00:00")
            ),
            transform=data.get("transform", None),
            camera=data.get("camera", None),
            presentation_params=presentation_params,
            historical_likes=data["likes"],
            historical_views=data["views"],
            category=CATEGORY_REVERSE_MAP.get(data["category"], None),
        ),
    )


def create_formats_from_archive_data(formats_json, asset):
    for format_json in formats_json:
        format = PolyFormat.objects.create(
            asset=asset,
            format_type=format_json["formatType"],
        )

        if format_json.get("formatComplexity", None) is not None:
            format_complexity_json = format_json["formatComplexity"]
            format.triangle_count = format_complexity_json.get(
                "triangleCount", None
            )
            format.lod_hint = format_complexity_json.get("lodHint", None)
            format.save()

        root_resource_json = format_json["root"]
        url = root_resource_json["url"]
        root_resource_data = {
            "external_url": f"https://web.archive.org/web/{url}",
            "is_root": True,
            "format": format,
            "asset": asset,
            "contenttype": get_content_type(url),
        }

        PolyResource.objects.create(**root_resource_data)

        role = FORMAT_ROLE_MAP[root_resource_json["role"]]
        if role is not None:
            format.role = role
            format.save()

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


def handle_asset(asset_id, archive_data):

    is_valid = False

    for _format in archive_data["formats"]:
        if _format["formatType"] in VALID_TYPES:
            is_valid = True
            break

    if is_valid:

        asset, _ = get_or_create_asset(
            asset_id,
            archive_data
        )

        # Manually create thumbnails and assume that the files exist on B2 in the right place
        asset.thumbnail = f"poly/{asset.url}/thumbnail.png"
        asset.thumbnail_contenttype = "image/png"

        tag_set = set(archive_data["tags"])
        icosa_tags = []
        for tag in tag_set:
            obj, _ = Tag.objects.get_or_create(name=tag)
            icosa_tags.append(obj)
        asset.tags.set(list(icosa_tags))

        # Create formats from the archive data, for posterity
        create_formats_from_archive_data(archive_data["formats"], asset)

        # Re-save the asset to trigger model validation
        # (and because we've updated the thumbnail)
        asset.save()

    else:
        with open("./invalid_assets.log", "a") as log:
            log.write(f"{asset_id}\n")


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

        print("Importing...", end="\r")
        with open("./assets.jsonl", "r") as json_file:
            for line in json_file:
                archive_data = json.loads(line)
                asset_id = archive_data["assetId"]
                print(
                    f"Importing {asset_id}                 ",
                    end="\r",
                )

                handle_asset(
                    asset_id,
                    archive_data
                )

        print("Finished")


