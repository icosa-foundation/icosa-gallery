import json

from django.core.management.base import BaseCommand
from django.db.models import Q
from icosa.models import Format


class Command(BaseCommand):
    help = """Reports on preferred formats whose resources do not have a local url. Extremely temporary; Don't keep this around."""

    def handle(self, *args, **options):
        really_broken_assets = set()
        q = Q(root_resource__file__isnull=True) | Q(root_resource__file="")
        formats_to_fix = []
        external_preferred_formats = Format.objects.filter(
            is_preferred_for_gallery_viewer=True, root_resource__isnull=False
        ).filter(q)
        for format in external_preferred_formats:
            asset = format.asset
            other_preferred_formats = Format.objects.filter(asset=asset, is_preferred_for_gallery_viewer=True).exclude(
                id=format.id
            )
            bad_other_preferred_formats = other_preferred_formats.filter(q)
            if (
                other_preferred_formats.count() == 0
                or other_preferred_formats.count() == bad_other_preferred_formats.count()
            ):
                really_broken_assets.add(asset)
            else:
                # after some analysis, other_formats is always 1
                other = other_preferred_formats.first()
                thing = {
                    "asset_url": asset.url,
                    "has_blocks": asset.has_blocks,
                    "bad_format": {
                        "id": format.id,
                        "format_type": format.format_type,
                    },
                    "other": {
                        "id": other.id,
                        "format_type": other.format_type,
                    },
                    # "others_invalid": [
                    #     {
                    #         "id": x.id,
                    #         "format_type": x.format_type,
                    #     }
                    #     for x in bad_other_preferred_formats
                    # ],
                }
                formats_to_fix.append(thing)

        print(f"really broken: {len(really_broken_assets)}")
        print(f"to fix: {len(formats_to_fix)}")

        with open("formats_to_fix.json", "w") as f:
            f.write(json.dumps(formats_to_fix))
