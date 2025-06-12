import json
import os
import secrets
from datetime import datetime

from django.core.management.base import BaseCommand
from icosa.helpers.file import is_gltf2
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import (
    CATEGORY_CHOICES,
    Asset,
    Format,
    Resource,
    Tag,
    User,
)

IMPORT_SOURCE = "google_poly"

POLY_JSON_DIR = "polygone_data"
ASSETS_JSON_DIR = f"{POLY_JSON_DIR}/assets"


EXTENSION_ROLE_MAP = {
    ".tilt": "POLYGONE_TILT_FORMAT",
    ".blocks": "POLYGONE_BLOCKS_FORMAT",
    ".glb": "POLYGONE_GLB_FORMAT",
    ".gltf": "POLYGONE_GLTF_FORMAT",
    ".obj": "POLYGONE_OBJ_FORMAT",
    ".fbx": "POLYGONE_FBX_FORMAT",
}

CATEGORY_REVERSE_MAP = dict([(x[1], x[0]) for x in CATEGORY_CHOICES])

# Only one of these should be enabled at any given time, but other than b2
# access and slowdown, there is no harm to the data by enabling them both.
PROCESS_VIA_JSON_OVERRIDES = True
PROCESS_VIA_GLTF_PARSING = False


def update_or_create_asset(directory, data):
    user, _ = User.objects.get_or_create(
        url=data["authorId"],
        defaults={
            "password": secrets.token_bytes(16),
            "displayname": data["authorName"],
            "imported_from": IMPORT_SOURCE,
        },
    )
    presentation_params = data.get("presentationParams", {})

    license = data.get("licence", "")
    if license in ["CREATIVE_COMMONS_BY", "CREATIVE_COMMONS_BY_ND"]:
        license = f"{license}_3_0"

    return Asset.objects.update_or_create(
        url=directory,
        defaults=dict(
            presentation_params=presentation_params,
        ),
        create_defaults=dict(
            name=data["name"],
            id=generate_snowflake(),
            imported_from=IMPORT_SOURCE,
            formats="",
            owner=user,
            description=data.get("description", None),
            visibility=data["visibility"],
            curated=data.get("curated"),
            polyid=directory,
            polydata=data,
            license=license,
            create_time=datetime.fromisoformat(data["createTime"].replace("Z", "+00:00")),
            update_time=datetime.fromisoformat(data["updateTime"].replace("Z", "+00:00")),
            transform=data.get("transform", None),
            camera=data.get("camera", None),
            presentation_params=presentation_params,
            historical_likes=data["likes"],
            historical_views=data["views"],
            category=CATEGORY_REVERSE_MAP.get(data["category"], None),
        ),
    )


def create_formats(directory, gltf2_data, formats_json, asset):
    done_thumbnail = False
    for format_json in formats_json:
        format = Format.objects.create(
            asset=asset,
            format_type=format_json["formatType"],
        )
        if format_json.get("formatComplexity", None) is not None:
            format_complexity_json = format_json["formatComplexity"]
            format.triangle_count = format_complexity_json.get("triangleCount", None)
            format.lod_hint = format_complexity_json.get("lodHint", None)
            format.save()

        # Manually create thumbnails from our assumptions about the data.
        if not done_thumbnail:
            asset.thumbnail = f"poly/{directory}/thumbnail.png"
            asset.thumbnail_contenttype = "image/png"
            asset.save()
        done_thumbnail = True
        root_resource_json = format_json["root"]

        file_path = root_resource_json["relativePath"]
        extension = os.path.splitext(file_path)[-1].lower()

        root_resource_data = {
            "file": f"poly/{directory}/{file_path}",
            "asset": asset,
            "format": format,
            "contenttype": root_resource_json["contentType"],
        }
        root_resource = Resource.objects.create(**root_resource_data)
        format.add_root_resource(root_resource)

        role = EXTENSION_ROLE_MAP.get(extension)
        format.role = role
        format.save()

        if PROCESS_VIA_JSON_OVERRIDES:
            # Retrospectively override the parent Format's type if we find a
            # special case.
            gltf_override_key = f"{directory}\\{file_path}"
            if gltf2_data.get(gltf_override_key, False):
                # print(f"Overwriting format_type for {gltf_override_key}")
                format.format_type = "GLTF2"
                format.save()

        if PROCESS_VIA_GLTF_PARSING:
            # Don't trust the format_type we got from the json. Instead, parse
            # the gltf to work out if it's version 1 or 2.
            if extension == ".gltf":
                if is_gltf2(root_resource.file.file):
                    format.format_type = "GLTF2"
                else:
                    format.format_type = "GLTF"
                format.save()

        if format_json.get("resources", None) is not None:
            for resource_json in format_json["resources"]:
                file_path = resource_json["relativePath"]

                resource_data = {
                    "file": f"poly/{directory}/{file_path}",
                    "format": format,
                    "asset": asset,
                    "contenttype": resource_json["contentType"],
                }
                Resource.objects.create(**resource_data)


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
        print("This is a stub. Doing nothing")
        return

        print("Importing...", end="\r")
        with open(os.path.join(POLY_JSON_DIR, "gltf2.json")) as g:
            gltf2_data = json.load(g)

            # TODO make user data file name configurable
            with open("./all_user_data.jsonl", "r") as json_file:
                for line in json_file:
                    archive_data = json.loads(line)
                    asset_id = archive_data["assetId"]
                    print(
                        f"Importing {asset_id}                 ",
                        end="\r",
                    )

                    asset, asset_created = update_or_create_asset(
                        asset_id,
                        archive_data,
                    )
                    if asset_created:
                        tag_set = set(archive_data["tags"])
                        icosa_tags = []
                        for tag in tag_set:
                            obj, _ = Tag.objects.get_or_create(name=tag)
                            icosa_tags.append(obj)
                        asset.tags.set(list(icosa_tags))

                        create_formats(
                            asset_id,
                            gltf2_data,
                            asset,
                        )

                        # Re-save the asset to trigger model
                        # validation.
                        asset.save()

        print("Finished                                  ")
