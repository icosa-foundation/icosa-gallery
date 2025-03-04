import json
from datetime import datetime

from django.core.management.base import BaseCommand
from icosa.models import Asset

POLY_JSON_DIR = "polygone_data"
ASSETS_JSON_DIR = f"{POLY_JSON_DIR}/assets"


def set_asset_update_time(asset_id, data):
    print(
        f"Importing {asset_id}                 ",
        end="\r",
    )
    try:
        asset = Asset.objects.get(url=asset_id)
        asset.update_time = datetime.fromisoformat(
            data["updateTime"].replace("Z", "+00:00")
        )
        asset.save(update_timestamps=False)
    except Asset.DoesNotExist:
        print(f"Not found: {asset_id}")


class Command(BaseCommand):
    help = """
    Resets the update_time field on all Assets that were imported via
    import_poly_assets management command.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            nargs="*",
            help="Space-separated list of specific IDs to import.",
            default=[],
            type=str,
        )

    def handle(self, *args, **options):
        with open("./all_data.jsonl", "r") as json_file:
            for line in json_file:
                data = json.loads(line)
                asset_id = data["assetId"]
                set_asset_update_time(asset_id, data)

        print("Finished                                  ")
