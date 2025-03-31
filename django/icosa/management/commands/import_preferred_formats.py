import json
import os

from django.core.management.base import BaseCommand
from icosa.models import Asset

JSONL_PATH = "preferred_formats.jsonl"


class Command(BaseCommand):
    def handle(self, *args, **options):
        with open(JSONL_PATH, "r") as json_file:
            for line in json_file:
                json_line = json.loads(line)
                asset_url = json_line["asset_url"]
                print(f"Importing {asset_url}")

                asset = Asset.objects.get(url=asset_url)

                # Skip if is_viewer_compatible is true; we either don't need to
                # operate on this file, or we already have in a previous run.
                if asset.is_viewer_compatible:
                    continue

                # NOTE: this get assumes there are no duplicate roles in this data
                # set at this time.
                format = asset.format_set.get(role=json_line["role"])
                format.format_type = json_line["format_type"]
                format.root_resource.file = json_line["root_resource"]
                resources = list(format.resource_set.all())
                for resource_file_name in json_line["resources"]:
                    filename = os.path.basename(resource_file_name)
                    # Find the resource object we want to operate on based on
                    # the filename we have in the jsonl.
                    # This should hard fail instead of choosing the first one
                    resource_obj = [x for x in resources if str(x.file).endswith(filename)][0]
                    resource_obj.file = resource_file_name
                    resource_obj.save()
                format.save()
                # We are saving this to correctly set is_viewer_compatible.
                asset.save(update_timestamps=False)
                # TODO remove this return, it's for safety
                return
