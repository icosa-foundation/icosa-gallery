import json

from django.core.management.base import BaseCommand
from django_project import settings
from icosa.models import (
    Asset,
    Format
)
import os
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry

retry_strategy = Retry(
    total=4,  # Maximum number of retries
    backoff_factor=2,  # Exponential backoff factor (e.g., 2 means 1, 2, 4, 8 seconds, ...)
    status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry on
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session = requests.Session()
session.mount('http://', adapter)
session.mount('https://', adapter)


class Command(BaseCommand):

    help = "Copies preferred viewable format from remote to local storage"

    def handle(self, *args, **options):
        root = os.path.abspath(os.path.join(settings.BASE_DIR, settings.MEDIA_ROOT))
        for asset in Asset.objects.all():

            # Skip assets that are owned by stores with too many assets
            if asset.owner.displayname in [
                "Sora Cycling",
                "Jasmine Roberts",
                "Verge Sport",
                "Endless Prowl",
                "arman apelo",
                "Rovikov"
            ]:
                continue

            preferred = asset._preferred_viewer_format
            root_resource = preferred["resource"]
            root_format = Format.objects.get(root_resource=root_resource)
            resources = list(root_format.resource_set.all())
            # Root root_resource is not included in the root_resource set
            resources.insert(0, root_resource)
            # if os.path.exists(resource_full_path) root_format.format_type:
            #     print(f"{root_resource.format.format_type}")

            # TODO this requires a thumbnail url field
            # thumbnail_url = asset.thumbnail_url
            # if thumbnail_url:
            #     thumbnail_dir = os.path.join(root, str(asset.url))
            #     thumbnail_path = os.path.join(thumbnail_dir, "thumbnail.png")
            #     if not os.path.exists(thumbnail_path):
            #         os.makedirs(thumbnail_dir, exist_ok=True)
            #         response = session.get(thumbnail_url, allow_redirects=True)
            #         with open(thumbnail_path, "wb") as f:
            #             f.write(response.content)
            #     asset.thumbnail.file = thumbnail_path

            is_root = True
            for root_resource in resources:
                resource_url = root_resource.external_url
                if not resource_url:
                    continue
                if is_root:
                    resource_base, resource_filename = resource_url.rsplit("/", 1)
                else:
                    resource_filename = resource_url[len(resource_base) + 1:]

                resource_filename = re.sub(r'[<>:"|?*]', '-', resource_filename)
                resource_full_path = os.path.join(root, str(asset.url), resource_filename)
                resource_full_path = resource_full_path.replace("\\", "/")
                resource_dir = os.path.dirname(resource_full_path)
                # print(f"Downloading {resource_full_path} to {resource_dir} for {asset.url} {asset.name} ({asset.owner.displayname})")

                if not os.path.exists(resource_full_path):
                    os.makedirs(resource_dir, exist_ok=True)
                    print("Downloading", resource_url, "to", resource_full_path)
                    response = session.get(resource_url, allow_redirects=True)
                    with open(resource_full_path, "wb") as f:
                        f.write(response.content)

                if is_root and resource_filename.endswith(".gltf"):
                    invalid = False
                    with open(resource_full_path, "rb") as f:
                        content = f.read()
                        try:
                            gltf_json = json.loads(content.decode("utf-8", errors="replace"))
                        except:
                            print(f"Invalid GLTF JSON: {resource_full_path[len(root):]}:  {content[:10].decode("utf-8", errors="replace")}")
                            invalid = True

                    if not invalid:
                        is_v2 = not isinstance(gltf_json.get("buffers", None), dict)
                        if not is_v2:
                            print(f"Found GLTF v1 instead of v2: {resource_full_path[len(root):]}")


                # Canonicalize the path
                resource_full_path = os.path.abspath(resource_full_path)
                if not resource_full_path.startswith(root):
                    print(f"Invalid path: {resource_full_path}")
                    print(f"Root: {root}")
                    assert False

                relative_path = resource_full_path[len(root):]
                root_resource.file = relative_path
                # root_resource.external_url = None
                root_resource.save()
                # print(f"asset: {asset.url}, file: {root_resource.file}, url: {root_resource.external_url}")
                # Only the first root_resource is the root root_resource
                is_root = False

            asset.save(update_timestamps=False)
