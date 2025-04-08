import json
import os
import secrets
from datetime import datetime
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django_project import settings
from icosa.helpers.file import get_content_type, is_gltf2
from icosa.helpers.format_roles import EXTENSION_ROLE_MAP
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.storage import get_b2_bucket
from icosa.models import (
    ASSET_STATE_COMPLETE,
    CATEGORY_LABELS,
    Asset,
    AssetOwner,
    Format,
    Resource,
    Tag,
)

# IMPORT_SOURCE = "google_poly"
IMPORT_SOURCE = "internet_archive_extras"

# WARNING This is currently unsafe if set to True
UPDATE_EXISTING = False

# This only works with genuine locally stored media
# and needs rewriting if you are using remote storage (i.e. S3)
CONVERT_AND_DOWNLOAD_THUMBNAILS = False

# POLY_JSON_DIR = "polygone_data"
# ASSETS_JSON_DIR = f"{POLY_JSON_DIR}/assets"

# POLY_GLTF_JSON_PATH = "C:\\poly_megajson\\poly.google.com\\view\\gltf_overrides.json"
# POLY_MEGAJSON_PATH = "C:\\poly_megajson\\poly.google.com\\view\\all_data.jsonl"
# ASSETS_JSON_DIR = "C:\\Users\\andyb\\Documents\\polygone.art\\assets"
POLY_GLTF_JSON_PATH = "gltf2.json"
POLY_MEGAJSON_PATH = "all_data.jsonl"
ASSETS_JSON_DIR = "polygone_data/assets"

FORMAT_ROLE_CHOICES = {
    1: "Original OBJ File",
    2: "Tilt File",
    4: "Unknown GLTF File A",
    6: "Original FBX File",
    7: "Blocks File",
    8: "USD File",
    11: "HTML File",
    12: "Original glTF File",
    13: "TOUR CREATOR EXPERIENCE",
    15: "JSON File",
    16: "lullmodel File",
    17: "SAND File A",
    18: "GLB File",
    19: "SAND File B",
    20: "SANDC File",
    21: "PB File",
    22: "Unknown GLTF File B",
    24: "Original Triangulated OBJ File",
    25: "JPG BUGGY",
    26: "USDZ File",
    30: "Updated glTF File",
    32: "Editor settings pb file",
    35: "Unknown GLTF File C",
    36: "Unknown GLB File A",
    38: "Unknown GLB File B",
    39: "TILT NATIVE glTF",
    40: "USER SUPPLIED glTF",
}

FORMAT_ROLE_MAP = {x[1]: x[0] for x in FORMAT_ROLE_CHOICES.items()}

VALID_TYPES = [x.replace(".", "").upper() for x in EXTENSION_ROLE_MAP.keys()]

CATEGORY_REVERSE_MAP = dict([(x[1], x[0]) for x in CATEGORY_LABELS])

# Only one of these should be enabled at any given time, but other than b2
# access and slowdown, there is no harm to the data by enabling them both.
PROCESS_VIA_JSON_OVERRIDES = True
PROCESS_VIA_GLTF_PARSING = False

IGNORE_SCRAPED_DATA = True


def get_json_from_b2(dir):
    bucket = get_b2_bucket()
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


def get_or_create_asset(directory, data, curated=False):
    owner, _ = AssetOwner.objects.get_or_create(
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
            owner=owner,
            description=data.get("description", None),
            visibility=data["visibility"],
            curated=curated,
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


def create_formats_from_scraped_data(directory, gltf2_data, formats_json, asset):
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

        # Manually create thumbnails and assume that the files exist on B2 in
        # the right place.
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
            # Note: This code will over-match and set all GLTFs to GLTF2 given
            # the right pathological data. However in the case of the polygone
            # scrape, we know that for each root resource, there is only one
            # file with the name {file_path} and so this is ok to blindly set
            # it to GLTF2.
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


def create_formats_from_archive_data(formats_json, asset):
    # done_thumbnail = False
    for format_json in formats_json:
        # Not sure if this is a safe assumption for existing data so only run when only adding new assets
        if not UPDATE_EXISTING:
            if "root" in format_json and format_json["root"]["role"] == "Updated glTF File":
                format_json["formatType"] = "GLTF2"

        format = Format.objects.create(
            asset=asset,
            format_type=format_json["formatType"],
        )

        if format_json.get("formatComplexity", None) is not None:
            format_complexity_json = format_json["formatComplexity"]
            format.triangle_count = format_complexity_json.get("triangleCount", None)
            format.lod_hint = format_complexity_json.get("lodHint", None)
            format.save()

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
            "asset": asset,
            "format": format,
            "contenttype": get_content_type(url),
        }

        root_resource = Resource.objects.create(**root_resource_data)

        role = FORMAT_ROLE_MAP[root_resource_json["role"]]
        format.add_root_resource(root_resource)
        format.role = role
        format.save()

        if format_json.get("resources", None) is not None:
            for resource_json in format_json["resources"]:
                url = resource_json["url"]
                resource_data = {
                    "external_url": f"https://web.archive.org/web/{url}",
                    "format": format,
                    "asset": asset,
                    "contenttype": get_content_type(url),
                }
                Resource.objects.create(**resource_data)
            # If a format has many files associated with it (i.e. it has a
            # `resources` key), then we want to grab the archive url if we have
            # it so we can provide this in the download options for the user.
            if format_json.get("archive", None):
                format.zip_archive_url = format_json["archive"]["url"]
                format.save()


def dedup_scrape_formats(formats, asset_id):
    new_formats = []
    dup_types = {}

    # Check json for duplicate gltf entries
    for format in formats:
        relative_path = format["root"]["relativePath"]
        if dup_types.get(relative_path):
            if relative_path != "model.gltf":
                print(
                    f"found duplicate for {asset_id} - \
                    {relative_path}"
                )
            continue
        new_formats.append(format)
        dup_types.update({relative_path: True})
    return new_formats


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
                "Finished downloading. Run this command again \
                without --download to process the files"
            )
            return

        if options["ids"]:
            directories = set(list(options["ids"]))
        else:
            directories = set(os.listdir(ASSETS_JSON_DIR))

        print("Importing...", end="\r")
        with open(POLY_GLTF_JSON_PATH, encoding="utf-8", errors="replace") as g:
            gltf2_data = json.load(g)
            # Loop through all entries in the big jsonl.
            #
            # If we find a matching entry in the poly scrape directory, create
            # an asset from the formats we find in there, then proceed to
            # create formats from the jsonl data.

            with open(POLY_MEGAJSON_PATH, "r") as json_file:
                for line in json_file:
                    archive_data = json.loads(line)
                    asset_id = archive_data["assetId"]
                    print(
                        f"Importing {asset_id}                 ",
                        end="\r",
                    )

                    if IGNORE_SCRAPED_DATA:
                        if asset_id in directories:
                            continue
                    else:
                        # Skip importing if the asset is not in the scraped
                        # json.
                        if asset_id not in directories:
                            continue

                    if IGNORE_SCRAPED_DATA:
                        # Create empty, dummy scrape data.
                        scrape_data = {
                            "tags": [],
                        }
                        scrape_formats = []
                        handle_asset(
                            asset_id,
                            archive_data,
                            scrape_data,
                            scrape_formats,
                            gltf2_data,
                        )

                    else:
                        # Create a new Asset object with the data.
                        full_path = os.path.join(ASSETS_JSON_DIR, asset_id, "data.json")
                        with open(full_path) as f:
                            scrape_data = json.load(f)
                            scrape_formats = dedup_scrape_formats(scrape_data["formats"], asset_id)
                        handle_asset(
                            asset_id,
                            archive_data,
                            scrape_data,
                            scrape_formats,
                            gltf2_data,
                        )

        print("Finished                                  ")


def handle_asset(
    asset_id,
    archive_data,
    scrape_data,
    scrape_formats,
    gltf2_data,
):
    is_valid = False
    for format in archive_data["formats"]:
        if format["formatType"] in VALID_TYPES:
            is_valid = True
            break
    if is_valid:
        asset, asset_created = get_or_create_asset(
            asset_id,
            archive_data,
            "curated" in scrape_data.get("tags", []),
        )

        if asset_created or UPDATE_EXISTING:
            tag_set = set(archive_data["tags"] + scrape_data["tags"])
            icosa_tags = []
            for tag in tag_set:
                obj, _ = Tag.objects.get_or_create(name=tag)
                icosa_tags.append(obj)
            asset.tags.set(list(icosa_tags))

            if not IGNORE_SCRAPED_DATA:
                # Create formats from the scraped data. These will
                # be our primary formats to use for the viewer,
                # initially.
                create_formats_from_scraped_data(
                    asset_id,
                    gltf2_data,
                    scrape_formats,
                    asset,
                )

            if UPDATE_EXISTING:
                asset.format_set.all().delete()
            # Create formats from the archive data, for
            # posterity.
            create_formats_from_archive_data(
                archive_data["formats"],
                asset,
            )

            # Re-save the asset to trigger model
            # validation.
            asset.save()

        if CONVERT_AND_DOWNLOAD_THUMBNAILS:
            thumbnail_url = archive_data["thumbnail_url"]
            root = settings.MEDIA_ROOT
            if thumbnail_url:
                thumbnail_dir = os.path.join(root, str(asset_id))
                thumbnail_path = os.path.join(thumbnail_dir, "thumbnail.png")
                if not os.path.exists(thumbnail_path):
                    os.makedirs(thumbnail_dir, exist_ok=True)
                    response = requests.get(thumbnail_url)
                    with open(thumbnail_path, "wb") as f:
                        f.write(response.content)
                asset.thumbnail = thumbnail_path[len(root) :]
                asset.save()
        else:
            if not settings.LOCAL_MEDIA_STORAGE:
                asset.thumbnail = f"poly/{asset_id}/thumbnail.png"
                asset.save()

    else:
        with open("./invalid_assets.log", "a") as log:
            log.write(f"{asset_id}\n")
