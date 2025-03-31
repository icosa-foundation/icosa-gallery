import json
import os
import urllib.parse

from django.core.management.base import BaseCommand
from icosa.models import Asset, Resource

JSONL_PATH = "preferred_formats.jsonl"


class Command(BaseCommand):
    def handle(self, *args, **options):
        with open(JSONL_PATH, "r") as json_file:
            for line in json_file:
                json_line = json.loads(line)
                asset_url = json_line["asset_url"]

                # Intentional hard fail if not found.
                try:
                    asset = Asset.objects.get(url=asset_url)
                except Asset.DoesNotExist:
                    print(f"Asset {asset_url} not found")
                    continue
                except Asset.MultipleObjectsReturned:
                    print(f"Asset {asset_url} multiple objects returned")
                    continue

                # Skip if is_viewer_compatible is true; we either don't need to
                # operate on this file, or we already have in a previous run.
                if asset.is_viewer_compatible:
                    continue

                print(f"Importing {asset_url}")

                # NOTE: this get assumes there are no duplicate roles in this data
                # set at this time.
                format = asset.format_set.get(role=json_line["role"])
                format.format_type = json_line["format_type"]
                root_filename = json_line["root_resource"].replace("\\", "/")
                format.root_resource.file = root_filename
                for resource_file_name in json_line["resources"]:
                    resource_file_name = resource_file_name.replace("\\", "/")
                    filename = os.path.basename(resource_file_name.replace("\\", "/"))
                    # Find the resource object we want to operate on based on
                    # the filename we have in the jsonl.
                    # Intentional hard fail if not found.
                    try:
                        resource_obj = Resource.objects.get(format=format, external_url__endswith=filename)
                    except (Resource.DoesNotExist, Resource.MultipleObjectsReturned):
                        try:  # Nested try/except bad
                            resource_obj = Resource.objects.get(
                                format=format, external_url__endswith=urllib.parse.quote(filename)
                            )
                        except (Resource.DoesNotExist, Resource.MultipleObjectsReturned):
                            print(f"Resource not found for format {format.pk} and filename {filename}")
                            continue
                    resource_obj.file = resource_file_name
                    resource_obj.save()
                asset.preferred_viewer_format_override = format
                format.save()
                # We are saving this to correctly set is_viewer_compatible.
                asset.save(update_timestamps=False)
