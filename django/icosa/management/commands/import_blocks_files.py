import json
from dataclasses import dataclass

from icosa.models import Asset, PolyFormat, PolyResource

from django.core.management.base import BaseCommand

BLOCKS_TYPE = "BLOCKS"


@dataclass
class ProcessedRow:
    asset: Asset
    format: PolyFormat
    resource: PolyResource


def process_blocks_row(asset_id, resource_url):

    try:
        asset = Asset.objects.get(url=asset_id)
    except Asset.DoesNotExist:
        print(f"Asset `{asset_id}` does not exist. Skipping.")
        return None

    if PolyFormat.objects.filter(
        asset=asset,
        format_type=BLOCKS_TYPE,
    ).exists():
        print(f"BLOCKS format for asset `{asset_id}` exists. Skipping.")
        return None

    else:
        format = PolyFormat.objects.create(
            asset=asset,
            format_type=BLOCKS_TYPE,
        )
        root_resource_data = {
            "file": None,
            "external_url": resource_url,
            "is_root": True,
            "format": format,
            "asset": asset,
            "contenttype": "application/octet-stream",
            "role": 7,
        }
        resource = PolyResource.objects.create(**root_resource_data)

    return ProcessedRow(
        asset,
        format,
        resource,
    )


def get_blocks_resource(data):
    for format in data["formats"]:
        if format["root"]["role"] == "Blocks File":
            return format["root"]
    return None


class Command(BaseCommand):

    help = "Adds BLOCKS formats from a local tsv file"

    def handle(self, *args, **options):

        with open("./all_data.jsonl", "r") as json_file:
            json_list = list(json_file)

            for item in json_list:
                data = json.loads(item)
                blocks_resource = get_blocks_resource(data)
                if blocks_resource is not None:
                    asset_id = data["assetId"]
                    resource_url = blocks_resource["url"]
                    processed_row = process_blocks_row(asset_id, resource_url)
                    # Re-save the asset to trigger validation
                    if processed_row is not None:
                        processed_row.asset.save()
                else:
                    continue
