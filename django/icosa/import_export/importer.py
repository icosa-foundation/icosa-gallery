import json
from datetime import datetime

from django.contrib.auth import get_user_model
from icosa.helpers.snowflake import generate_snowflake
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
            # Currently only validating assets
            if data.get("object_type", "") == "asset":
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


def import_django_user(django_user_data):
    django_user_defaults = dict(django_user_data)
    del django_user_defaults["username"]
    # TODO(james): We don't have any user perms or groups at the moment, but we will need to handle these at some point.
    del django_user_defaults["groups"]
    del django_user_defaults["user_permissions"]

    # We can't use the create_user helper method, because we have the password
    # hash stored; create_user expects a raw password.
    django_user, created = User.objects.get_or_create(
        username=django_user_data["username"],
        defaults=django_user_defaults,
    )

    if not created:
        print(f"Skipped User {django_user_data['username']}. Already exists.")

    return django_user


def import_owner(asset_owner_data):
    asset_owner_defaults = dict(asset_owner_data)
    del asset_owner_defaults["url"]
    asset_owner_defaults["django_user"] = None
    asset_owner, created = AssetOwner.objects.get_or_create(
        url=asset_owner_data["url"],
        defaults=asset_owner_defaults,
    )
    if not created:
        print(f"Skipped AssetOwner {asset_owner_data['url']}. Already exists.")
        return asset_owner

    django_user_data = asset_owner_data.get("django_user", None)

    if django_user_data is None:
        return asset_owner

    django_user = import_django_user(django_user_data)

    asset_owner.django_user = django_user
    asset_owner.save()

    return asset_owner


def import_asset(data):
    asset_defaults = dict(data)
    asset_tags = asset_defaults.get("tags", [])
    asset_defaults["id"] = generate_snowflake()

    del asset_defaults["tags"]
    del asset_defaults["url"]
    del asset_defaults["owner"]
    del asset_defaults["format_set"]
    asset_defaults["thumbnail"] = strip_storage_root(asset_defaults["thumbnail"])
    asset_defaults["preview_image"] = strip_storage_root(asset_defaults["preview_image"])

    create_time = None
    update_time = None

    if asset_defaults.get("create_time") is not None:
        create_time = datetime.fromisoformat(asset_defaults["create_time"].replace("Z", "+00:00"))
        del asset_defaults["create_time"]
    if asset_defaults.get("update_time") is not None:
        update_time = datetime.fromisoformat(asset_defaults["update_time"].replace("Z", "+00:00"))
        del asset_defaults["update_time"]

    asset, asset_created = Asset.objects.get_or_create(url=data["url"], defaults=asset_defaults)

    if asset_tags:
        asset.tags.set(asset_tags)

    # Creating an asset gives it a `create_time` of `now`. Override this.
    if create_time is not None:
        asset.create_time = create_time
    if update_time is not None:
        asset.update_time = update_time
    asset.save(bypass_custom_logic=True)

    # The asset already exists. Currently, this means we will not create
    # formats and resources for it. This could change in future.
    if not asset_created:
        print(f"Skipped Asset {data['url']}. Already exists.")
        return

    # Create formats and their resources
    format_set_data = data["format_set"]

    for format_data in format_set_data:
        format_defaults = dict(format_data)

        # Remove keys from a previous version of data export
        if "is_preferred_for_viewer" in format_defaults.keys():
            del format_defaults["is_preferred_for_viewer"]
        if "is_preferred_for_download" in format_defaults.keys():
            del format_defaults["is_preferred_for_download"]

        del format_defaults["id"]
        del format_defaults["resource_set"]
        del format_defaults["root_resource"]
        format_defaults["asset"] = asset
        format = Format.objects.create(**format_defaults)
        if format_data["root_resource"]:
            root_resource_defaults = dict(format_data["root_resource"])
            del root_resource_defaults["id"]
            root_resource_defaults["asset"] = asset
            root_resource_defaults["file"] = strip_storage_root(root_resource_defaults["file"])
            Resource.objects.create(**root_resource_defaults)
        for resource_data in format_data["resource_set"]:
            resource_defaults = dict(resource_data)
            del resource_defaults["id"]
            resource_defaults["format"] = format
            resource_defaults["file"] = strip_storage_root(resource_defaults["file"])
            Resource.objects.create(**root_resource_defaults)
    asset.assign_preferred_viewer_format()

    # Create asset owner
    # TODO: do we change the `imported` field? Seems like `imported` should be
    # a string, not a boolean.
    asset_owner_data = data.get("owner", None)
    if asset_owner_data is None:
        return

    asset_owner = import_owner(asset_owner_data)
    asset.owner = asset_owner
    asset.save(bypass_custom_logic=True)


def do_import(file_name: str):
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
        for i, line in enumerate(json_file, 1):
            data = json.loads(line)
            object_type = data.get("object_type", None)
            if object_type not in ["asset", "owner", "user"]:
                print(f"Skipping line {i}: object_type not one of 'asset', 'owner', or 'user'.")
            del data["object_type"]

            # Debug
            # for k in data.keys():
            #     print(k, data[k])

            if object_type == "user":
                print("Importing User")
                import_django_user(data)
            if object_type == "owner":
                print("Importing Owner")
                import_owner(data)
            if object_type == "asset":
                print("Importing Asset")
                import_asset(data)
