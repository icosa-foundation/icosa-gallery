from icosa.helpers.file import get_content_type
from icosa.models import Asset, PolyFormat, PolyResource

from django.core.management.base import BaseCommand

STORAGE_ROOT = "https://f005.backblazeb2.com/file/icosa-gallery/"


class Command(BaseCommand):

    help = """Extracts format json into concrete models and converts to poly
    format."""

    def handle(self, *args, **options):
        assets = Asset.objects.filter(
            imported_from__isnull=True,
            formats__isnull=False,
        ).exclude(formats="", imported_from="")
        for idx, asset in enumerate(assets):
            # print(f"Processing {asset.id} ({idx} of {assets.count()})...")
            done_thumbnail = False
            for format_json in asset.formats:
                format_data = {
                    "format_type": format_json["format"],
                    "asset": asset,
                }
                format, created = PolyFormat.objects.get_or_create(
                    **format_data
                )
                if created:
                    file_path = format_json["url"].replace(
                        STORAGE_ROOT,
                        "",
                    )
                    root_resource_data = {
                        "file": file_path,
                        "is_root": True,
                        "asset": asset,
                        "format": format,
                        "contenttype": get_content_type(file_path),
                    }
                    PolyResource.objects.create(**root_resource_data)

                    if asset.thumbnail and done_thumbnail is False:
                        asset_thumbnail = asset.thumbnail
                        asset.thumbnail_contenttype = get_content_type(
                            asset_thumbnail.name
                        )
                        print(asset.thumbnail, asset.thumbnail_contenttype)
                        asset.save()
                        done_thumbnail = True
                    if format_json.get("subfiles", None) is not None:
                        for resource in format_json["subfiles"]:
                            resource_data = {
                                "file": resource["url"].replace(
                                    STORAGE_ROOT,
                                    "",
                                ),
                                "is_root": False,
                                "asset": asset,
                                "format": format,
                                "contenttype": get_content_type(file_path),
                            }
                            PolyResource.objects.create(**resource_data)
