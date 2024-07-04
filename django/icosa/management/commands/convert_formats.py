import json
import os

from icosa.models import Asset, PolyFormat, PolyResource

from django.core.management.base import BaseCommand


class Command(BaseCommand):

    help = """Extracts format json into concrete models and converts to poly
    format."""

    def handle(self, *args, **options):
        print(
            "Not fully tested. Please comment out the early return in this command to run on your local data."
        )
        return
        assets = Asset.objects.filter(
            imported=False,
            formats__isnull=False,
        ).exclude(formats="")
        skipped_assets = []
        for idx, asset in enumerate(assets):
            print(
                f"\tProcessing {asset} - {asset.id} ({idx} of {assets.count()})..."
            )
            preferred_format = asset.preferred_format
            if preferred_format is None:
                print(
                    f"Cannot determine preferred format for {asset} - {asset.id}"
                )
                skipped_assets.append(asset)
                continue
            format_data = {
                "format_type": preferred_format["format"],
                "asset": asset,
            }
            format, created = PolyFormat.objects.get_or_create(**format_data)
            if created:
                for main_format in asset.formats:
                    resource_data = {
                        "file": main_format["url"].replace(
                            "https://f005.backblazeb2.com/file/icosa-gallery/",
                            "",
                        ),
                        "is_root": True,
                        "format": format,
                    }
                    main_resource = PolyResource(**resource_data)
                    main_resource.save()

                    if main_format.get("subfiles", None) is not None:
                        for sub_format in main_format["subfiles"]:
                            sub_resource_data = {
                                "file": sub_format["url"].replace(
                                    "https://f005.backblazeb2.com/file/icosa-gallery/",
                                    "",
                                ),
                                "format": format,
                                "is_root": False,
                            }
                            sub_format = PolyResource(**sub_resource_data)
                            sub_format.save()
        print(f"Skipped {len(skipped_assets)} assets.")
