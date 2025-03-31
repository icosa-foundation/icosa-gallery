import json
import os
import secrets
from datetime import datetime
from pathlib import Path

import requests
from django.core.management.base import BaseCommand
from django_project import settings
from icosa.helpers.file import get_content_type, is_gltf2
from icosa.helpers.format_roles import EXTENSION_ROLE_MAP
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.storage import get_b2_bucket
from icosa.models import (
    ASSET_STATE_COMPLETE,
    CATEGORY_LABELS,
    Asset,
    AssetOwner,
    Format,
    Resource,
    Tag,
)

JSONL_PATH = "all_data.jsonl"


class Command(BaseCommand):
    def handle(self, *args, **options):
        with open(JSONL_PATH, "r") as json_file:
            for line in json_file:
                json_line = json.loads(line)
                asset_url = json_line["asset_url"]
                print(f"Importing {asset_url}")
            asset = Asset.objects.get(url=asset_url)
            format = asset.format_set.get(role=json_line["role"])
            format.format_type = json_line["format_type"]
            format.root_resource.file = json_line["root_resource"]
            existing_resources = list(format.resource_set.all())
            for resource in json_line["resources"]:
                filename = os.path.basename(resource)
                resource_obj = [x for x in existing_resources if str(x.file).endswith(filename)].first()
                resource_obj.file = resource
                resource_obj.save()
            format.save()
            asset.save(update_timestamps=False)
