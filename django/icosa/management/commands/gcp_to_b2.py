import json
import os

from django.core.management.base import BaseCommand
from icosa.models import Asset


class Command(BaseCommand):
    help = """Swaps Assets' hard-coded storage bucket references from Google
    Cloud Platform to Backblaze B2"""

    def handle(self, *args, **options):
        GCP_URL = os.environ.get("GCP_URL")
        B2_URL = os.environ.get("B2_URL")
        if not GCP_URL or not B2_URL:
            print("must set GCP_URL and B2_URL in your .env file")
            return

        assets_with_formats = Asset.objects.filter(formats__icontains=GCP_URL)
        assets_with_thumbnails = Asset.objects.filter(thumbnail__icontains=GCP_URL)

        for asset in assets_with_formats:
            format_str = json.dumps(asset.formats)
            asset.formats = json.loads(format_str.replace(GCP_URL, B2_URL))
            asset.save()

        for asset in assets_with_thumbnails:
            url = asset.thumbnail.name.replace(GCP_URL, "icosa/")
            asset.thumbnail = url
            asset.save()
