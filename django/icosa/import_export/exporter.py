import json

from django.core.serializers import serialize
from django.db.models import Model, Q
from django.utils import timezone
from icosa.models import Asset

# TODO: Don't hard-code this
STORAGE_ROOT = "https://f005.backblazeb2.com/file/icosa-gallery/"


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


def export_assets(
    asset_ids: list[int] = [],
    owner_ids: list[int] = [],
    user_ids: list[int] = [],
):
    q = Q()
    if asset_ids:
        q &= Q(id__in=asset_ids)
    if owner_ids:
        q &= Q(asset_owner__id__in=owner_ids)
    if user_ids:
        q &= Q(asset_owner__django_user__id__in=user_ids)
    assets = Asset.objects.filter(q)

    export_timestamp = timezone.now().strftime("%d-%m-%y_%H-%M-%S")

    with open(f"asset_export-{export_timestamp}.jsonl", "a") as f:
        print(f"todo: {assets.count()} assets.")
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
                owner_data = obj_to_dict(asset.owner)
                if asset.owner.django_user:
                    # TODO: This exports the django user's password hash. Not
                    # as terrible as plain text, but perhaps we should warn the
                    # operating user that we are doing this.
                    owner_data["django_user"] = obj_to_dict(asset.owner.django_user)
                asset_data["owner"] = owner_data
            line_out = json.dumps(asset_data)
            f.write(line_out + "\n")

            if i and i % 1000 == 0:
                print(f"done {i}")
