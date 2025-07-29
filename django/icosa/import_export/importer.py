import json

from django.contrib.auth import get_user_model
from icosa.models import Asset, AssetOwner, Format, Resource

# TODO: Don't hard-code this
STORAGE_ROOT = "https://f005.backblazeb2.com/file/icosa-gallery/"
User = get_user_model()


def strip_storage_root(s: str) -> str:
    if s is None or s == "" or not s.startswith(STORAGE_ROOT):
        return s
    return s.replace(STORAGE_ROOT, "")


def validate_data(file_name: str) -> tuple[bool, int, str]:
    # TODO: This is a work in progress sketch of what validation might look
    # like. Not needed straight away.
    print("Validating input data")
    keys_to_test = ["format_set"]
    subkeys_to_test = [["format_set", "resource_set"]]
    is_valid = True
    error_line = 0
    error_message = ""
    with open(file_name, "r") as json_file:
        for i, line in enumerate(json_file, 1):
            data = json.loads(line)
            for key in keys_to_test:
                try:
                    data[key]
                except KeyError as e:
                    is_valid = False
                    error_line = i
                    error_message = e
                    break
            for key in subkeys_to_test:
                try:
                    k1 = data[key[0]]
                    if type(k1) is list:
                        for item in k1:
                            item[key[1]]
                    if type(k1) is dict:
                        k1[key[1]]
                except KeyError as e:
                    is_valid = False
                    error_line = i
                    error_message = e
                    break
    return (is_valid, error_line, error_message)


def import_assets(file_name: str):
    # TODO: importing from a jsonl file is just one way to ingest data. It
    # would be nice to have a bunch of sources that we car try_into jsonl.
    if not file_name.endswith(".jsonl"):
        raise ValueError("Must specify a .jsonl file to import from")
    is_valid, error_line, error_message = validate_data(file_name)

    # If validation is solid, the importer code below is perhaps easier to read
    # without error-handling.
    if not is_valid:
        raise ValueError(f"Error at line {error_line}: {error_message}")

    with open(file_name, "r") as json_file:
        for line in json_file:
            data = json.loads(line)
            asset_defaults = dict(data)
            del asset_defaults["owner"]
            del asset_defaults["format_set"]
            asset_defaults["thumbnail"] = strip_storage_root(asset_defaults["thumbnail"])
            asset_defaults["preview_image"] = strip_storage_root(asset_defaults["preview_image"])
            asset, asset_created = Asset.objects.get_or_create(id=data["id"], defaults=asset_defaults)

            # The asset already exists. Currently, this means we will not
            # create formats and resources for it. This could change in future.
            if not asset_created:
                continue

            # Create formats and their resources
            format_set_data = data["format_set"]
            for format_data in format_set_data:
                format_defaults = dict(format_data)
                del format_defaults["resource_set"]
                del format_defaults["root_resource"]
                format_defaults["asset"] = asset
                format = Format.objects.create(**format_defaults)
                if format_data["root_resource"]:
                    root_resource_defaults = dict(format_data["root_resource"])
                    root_resource_defaults["asset"] = asset
                    root_resource_defaults["file"] = strip_storage_root(root_resource_defaults["file"])
                    Resource.objects.create(**root_resource_defaults)
                for resource_data in format_data["resource_set"]:
                    resource_defaults = dict(resource_data)
                    resource_defaults["format"] = format
                    resource_defaults["file"] = strip_storage_root(resource_defaults["file"])
                    Resource.objects.create(**root_resource_defaults)
