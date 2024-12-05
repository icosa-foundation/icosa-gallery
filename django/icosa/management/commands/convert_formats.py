import os

from icosa.helpers.file import get_content_type, get_role_id_from_file
from icosa.models import Asset, PolyFormat, PolyResource

from django.core.management.base import BaseCommand
from django.db.models import Q

STORAGE_ROOT = "https://f005.backblazeb2.com/file/icosa-gallery/"


class Command(BaseCommand):

    help = """Extracts format json into concrete models and converts to poly
    format."""

    def handle(self, *args, **options):
        assets = Asset.objects.filter(
            Q(imported_from__isnull=True) | Q(imported_from="")
        ).exclude(Q(formats__isnull=True) | Q(formats=""))

        for idx, asset in enumerate(assets):
            done_thumbnail = False

            print(f"Processing {asset.id} ({idx} of {assets.count()})...")

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
                    name_and_extension = os.path.splitext(file_path)
                    file_name = name_and_extension[0].lower()
                    extension = name_and_extension[1].lower().replace(".", "")
                    role = get_role_id_from_file(file_name, extension)
                    format.role = role
                    format.save()

                    root_resource_data = {
                        "file": file_path,
                        "is_root": True,
                        "asset": asset,
                        "format": format,
                        "contenttype": get_content_type(file_path),
                    }
                    PolyResource.objects.create(**root_resource_data)

                    if asset.thumbnail and done_thumbnail is False:
                        asset.thumbnail_contenttype = get_content_type(
                            asset.thumbnail.name
                        )
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
