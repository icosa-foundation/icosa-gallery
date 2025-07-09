import json

from django.core.management.base import BaseCommand
from icosa.models import Asset

SMALL_SAMPLE = True


class Command(BaseCommand):
    def handle(self, *args, **options):
        if SMALL_SAMPLE:
            print("=" * 80)
            print("Running on a sample of the data because SMALL_SAMPLE == True")
            print("You do not want this in production.")
            print("=" * 80)

        with open("runtime_preferred_formats.jsonl", "w") as pf, open("runtime_downloads.jsonl", "w") as dl:
            assets = Asset.objects.all()
            if SMALL_SAMPLE:
                print(f"todo: {assets.count() / 100} assets.")
            else:
                print(f"todo: {assets.count()} assets.")
            for i, asset in enumerate(assets.iterator(chunk_size=1000)):
                if i and i % 1000 == 0:
                    print(f"done {i}")

                # It was getting tedious running this over and over.
                # This makes it 100x faster and 100x less complete.
                if i % 100 != 0 and SMALL_SAMPLE:
                    continue

                asset_id = asset.id
                p_format = asset.preferred_viewer_format
                if p_format:
                    try:
                        # Original data set where we would construct a dict ourselves.
                        format_data = {
                            "asset_id": asset_id,
                            "preferred_format": {
                                "format_id": p_format["format"].id if p_format["format"] else None,
                                "url": p_format["url"],
                                "resource_id": p_format["resource"].id if p_format["resource"] else None,
                            },
                        }
                    except TypeError:
                        # We are now returning a format object directly, so
                        # must construct the data differently. The heuristic
                        # for this is `TypeError: 'Format' objects is not
                        # subscriptable.
                        format_data = {
                            "asset_id": asset_id,
                            "preferred_format": {
                                "format_id": p_format.id if p_format else None,
                                "url": p_format.root_resource.internal_url_or_none if p_format.root_resource else None,
                                "resource_id": p_format.root_resource.id if p_format.root_resource else None,
                            },
                        }
                    pf.write(json.dumps(format_data))
                else:
                    pf.write(json.dumps({"asset_id": asset_id, "preferred_format": None}))
                pf.write("\n")

                dl_formats = asset.get_all_downloadable_formats()
                if dl_formats:
                    dl.write(json.dumps({"asset_id": asset_id, "formats": dl_formats}))
                else:
                    dl.write(json.dumps({"asset_id": asset_id, "formats": None}))
                dl.write("\n")
