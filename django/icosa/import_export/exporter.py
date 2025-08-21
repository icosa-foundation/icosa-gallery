import json

from django.contrib.auth import get_user_model
from django.core.serializers import serialize
from django.db.models import Model, Q
from django.utils import timezone
from icosa.models import Asset, AssetOwner

# TODO: Don't hard-code this
STORAGE_ROOT = "https://f005.backblazeb2.com/file/icosa-gallery/"
User = get_user_model()


# Django's model_to_dict does not serialize all field types. This method gets
# us more of the way there.
def obj_to_dict(obj: Model) -> dict:
    json_data = json.loads(serialize("json", [obj]))[0]
    obj_data = json_data["fields"]
    obj_data.update({"id": json_data["pk"]})
    return obj_data


def prefix_storage_root(s: str) -> str:
    if s is None or s == "":
        return s
    return f"{STORAGE_ROOT}{s}"


def export_user(django_user):
    # TODO: This exports the django user's password hash. Not
    # as terrible as plain text, but perhaps we should warn the
    # operating user that we are doing this.
    return obj_to_dict(django_user)


def export_owner(owner):
    owner_data = obj_to_dict(owner)
    if owner.django_user:
        owner_data["django_user"] = export_user(owner.django_user)
    return owner_data


def do_export(
    asset_ids: list[int] = [],
    owner_ids: list[int] = [],
    user_ids: list[int] = [],
):
    asset_q = Q()
    if asset_ids:
        asset_q &= Q(id__in=asset_ids)
    if owner_ids:
        asset_q &= Q(owner__id__in=owner_ids)
    if user_ids:
        asset_q &= Q(owner__django_user__id__in=user_ids)
    assets = Asset.objects.filter(asset_q)

    export_timestamp = timezone.now().strftime("%d-%m-%y_%H-%M-%S")

    exported_owner_ids = set()
    exported_user_ids = set()

    with open(f"export-{export_timestamp}.jsonl", "a") as f:
        print(f"Exporting {assets.count()} assets with their owners and users.")
        for i, asset in enumerate(assets.iterator(chunk_size=1000)):
            # TODO: We need to be careful of `remix_ids` on the Asset. These
            # IDs will be the source system's IDs and might either not be
            # present in the destination, or will be the wrong assets. Should we
            # blank this field, or export full Assets listed here? Potential for export
            # size to explode if we do the latter. Perhaps this is user-selectable.
            asset_data = obj_to_dict(asset)

            # We need the full image url on the remote server, not just the path.
            asset_image_keys = ["thumbnail", "preview_image"]
            for key in asset_image_keys:
                asset_data[key] = prefix_storage_root(asset_data[key])

            formats = asset.format_set.all()
            format_set_data = []
            for format in formats:
                format_data = obj_to_dict(format)
                del format_data["asset"]
                if format.root_resource:
                    format_data["root_resource"] = obj_to_dict(format.root_resource)
                    format_data["root_resource"]["file"] = prefix_storage_root(format_data["root_resource"]["file"])
                else:
                    format_data["root_resource"] = None
                format_data["resource_set"] = []
                for resource in format.resource_set.all():
                    resource_data = obj_to_dict(resource)
                    del resource_data["asset"]
                    resource_data["file"] = prefix_storage_root(resource_data["file"])
                    format_data["resource_set"].append(resource_data)
                format_set_data.append(format_data)
            asset_data.update({"format_set": format_set_data})

            # TODO: This will not de-duplicate owners and users. I think this is ok for
            # a naive import of everything, but if this turns out to be very
            # wasteful, I should rethink this. We will need a more clever way of
            # making sure the right assets get the right owners, etc.
            if asset.owner:
                exported_owner_ids.add(asset.owner.id)
                if asset.owner.django_user:
                    exported_user_ids.add(asset.owner.django_user.id)
                asset_data["owner"] = export_owner(asset.owner)
            asset_data["object_type"] = "asset"
            line_out = json.dumps(asset_data)
            f.write(line_out + "\n")

            if i and i % 1000 == 0:
                print(f"Exported {i} of {len(assets)} assets.")

        owner_q = Q()
        if owner_ids:
            owner_q &= Q(id__in=owner_ids)
        if user_ids:
            owner_q &= Q(django_user__id__in=user_ids)

        if owner_ids or user_ids:
            owners = AssetOwner.objects.filter(owner_q).exclude(id__in=list(exported_owner_ids))
            print(
                f"Exporting {owners.count()} owners with their users. ({len(exported_owner_ids)} excluded as they were exported during asset export.)"
            )
            for i, owner in enumerate(owners.iterator(chunk_size=1000)):
                owner_data = export_owner(owner)
                owner_data["object_type"] = "owner"
                if owner.django_user:
                    exported_user_ids.add(owner.django_user.id)
                line_out = json.dumps(owner_data)
                f.write(line_out + "\n")

                if i and i % 1000 == 0:
                    print(f"Exported {i} of {len(owners)} owners.")

        if user_ids:
            users = User.objects.filter(id__in=user_ids).exclude(id__in=list(exported_user_ids))
            print(
                f"Exporting {users.count()} users. ({len(exported_user_ids)} excluded as they were exported during owner export.)"
            )
            for i, user in enumerate(users.iterator(chunk_size=1000)):
                user_data = export_user(user)
                user_data["object_type"] = "user"
                line_out = json.dumps(user_data)
                f.write(line_out + "\n")

                if i and i % 1000 == 0:
                    print(f"Exported {i} of {len(users)} users.")
        print("Done")
