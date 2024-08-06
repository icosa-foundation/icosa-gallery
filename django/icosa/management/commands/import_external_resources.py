import csv
from dataclasses import dataclass

from icosa.models import Asset, PolyFormat, PolyResource

from django.core.management.base import BaseCommand

BLOCKS_TYPE = "BLOCKS"


@dataclass
class ProcessedRow:
    asset: Asset
    format: PolyFormat
    resource: PolyResource


def process_row(row):
    asset_id = row[0]

    try:
        resource_url = row[1]
    except IndexError:
        print(f"No resource url for line `{asset_id}`. Skipping.")
        return None

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
        }
        resource = PolyResource.objects.create(**root_resource_data)

    return ProcessedRow(
        asset,
        format,
        resource,
    )


class Command(BaseCommand):

    help = "Adds BLOCKS formats from a local csv"

    def handle(self, *args, **options):

        with open("blocks.csv", "r") as f:
            reader = csv.reader(f, delimiter="\t")

            for row in reader:
                _ = process_row(row)
