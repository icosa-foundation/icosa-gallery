import json

from django.core.management.base import BaseCommand
from icosa.models import Asset


class Command(BaseCommand):
    def handle(self, *args, **options):
        with open("runtime_preferred_formats.jsonl", "w") as pf, open("runtime_downloads.jsonl", "w") as dl:
            assets = Asset.objects.all()
            print(f"todo: {assets.count()} assets.")
            for i, asset in enumerate(assets.iterator(chunk_size=1000)):
                if i and i % 1000 == 0:
                    print(f"done {i}")
                asset_id = asset.id
                p_format = asset.preferred_viewer_format
                if p_format:
                    pf.write(
                        json.dumps(
                            {
                                "asset_id": asset_id,
                                "preferred_format": {
                                    "format_id": p_format["format"].id if p_format["format"] else None,
                                    "url": p_format["url"],
                                    "resource_id": p_format["resource"].id if p_format["resource"] else None,
                                },
                            }
                        )
                    )
                else:
                    pf.write(json.dumps({"asset_id": asset_id, "preferred_format": None}))
                pf.write("\n")

                dl_formats = asset.get_all_downloadable_formats()
                if dl_formats:
                    dl.write(json.dumps({"asset_id": asset_id, "formats": dl_formats}))
                else:
                    dl.write(json.dumps({"asset_id": asset_id, "formats": None}))
                dl.write("\n")
