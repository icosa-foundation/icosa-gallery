import json
import os

from django.core.management.base import BaseCommand
from django_project import settings
from icosa.models import Asset

media_root = os.path.abspath(os.path.join(settings.BASE_DIR, settings.MEDIA_ROOT))


class Command(BaseCommand):
    def handle(self, *args, **options):
        with open("preferred_formats.jsonl", "w") as f:
            for asset in Asset.objects.all():
                # Skip assets that are owned by stores with too many assets
                if asset.owner.displayname in [
                    "Sora Cycling",
                    "Verge Sport",
                    "arman apelo",
                    "Rovikov",
                ]:
                    continue

                # Assume that the presence of a preferred viewer format means
                # that we have already processed this asset
                preferred_qs = asset.format_set.filter(is_preferred_for_viewer=True)

                if len(preferred_qs) == 0:
                    print(f"Asset has no preferred format: {asset.url}")
                    continue
                if len(preferred_qs) > 1:
                    print(f"Asset has multiple preferred formats: {asset.url}")
                    continue

                preferred = preferred_qs.first()
                resources = list(preferred.resource_set.all())
                json_line = {
                    "asset_url": asset.url,
                    "role": preferred.role,
                    "format_type": preferred.role,
                    "root_resource": str(preferred.root_resource.file),
                    "resources": [],
                }
                for sub_resource in resources:
                    json_line["resources"].append(str(sub_resource.file))
                line_out = json.dumps(json_line)
                f.write(line_out + "\n")
                # print(f"Exported asset: {asset.url}")
