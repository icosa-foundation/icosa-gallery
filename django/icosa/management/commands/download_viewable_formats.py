import json
import urllib

from django.core.management.base import BaseCommand

from django_project import settings
from icosa.models import (
    Asset,
    Format
)
import os
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

        skip = False
        for asset in Asset.objects.all():

            # Skip assets that are owned by stores with too many assets
            if asset.owner.displayname in [
                "Sora Cycling",
                "Verge Sport",
                "arman apelo",
                "Rovikov"
            ]:
                continue

            preferred = asset._preferred_viewer_format
            root_resource = preferred["resource"]
            root_format = Format.objects.get(root_resource=root_resource)
            resources = list(root_format.resource_set.all())

            # TODO Grab the GLTF1 format and use it later if the preferred GLTF uses the "technqiues" extension
            # unknown_gltf_q = Q(format__role=4) | Q(format__role=35)
            # fallback_format = asset.resource_set.filter(unknown_gltf_q).first()
            # print(dir(fallback_format))
            # fallback_resource = fallback_format.resource
            # fallback_resources = list(root_format.resource_set.all())

            # Root root_resource is not included in the root_resource set
            resources.insert(0, root_resource)

            # TODO this requires a thumbnail url field which we don't currently have
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

                if not resource_url: continue

                if is_root:
                    resource_base, resource_filename = resource_url.rsplit("/", 1)
                else:
                    resource_filename = resource_url[len(resource_base) + 1:]

                resource_rel_path = os.path.join(str(asset.url), resource_filename)
                resource_rel_path = resource_rel_path.replace("/", "\\")
                resource_rel_path = urllib.parse.unquote(resource_rel_path)

                # TODO See later note about where this breaks the relative path calculation
                # There are relative paths that start with c:\ or similar
                # which will break os.path.join on Windows
                resource_rel_path = resource_rel_path.replace(":", "%3A")
                resource_full_path = os.path.join(root, resource_rel_path)
                resource_dir = os.path.dirname(resource_full_path)

                if not os.path.exists(resource_full_path):
                    os.makedirs(resource_dir, exist_ok=True)
                    old_path = resource_full_path.replace("\\media\\", "\\media_old\\")
                    if os.path.exists(old_path):
                        os.rename(old_path, resource_full_path)
                        print(f"Restored {resource_full_path}")
                    else:
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

                    extensions = gltf_json.get("extensions", None)
                    if extensions is not None and extensions.get("GOOGLE_tilt_brush_material", None) is not None:
                        print(f"Has GOOGLE_tilt_brush_material: {resource_full_path[len(root):]}")
                    if extensions is not None and extensions.get("GOOGLE_tilt_brush_techniques", None) is not None:
                        print(f"Has techniques: {resource_full_path[len(root):]}")
                        skip = True
                        break

                # Canonicalize the path
                resource_full_path = os.path.abspath(resource_full_path)
                if not resource_full_path.startswith(root):
                    print(f"Invalid path: {resource_full_path}")

                # TODO This is buggy for assets where we replaced drive letters with %3A earlier
                relative_path = resource_full_path[len(root):]
                root_resource.file = relative_path

                # Do we want to clear external_url?
                # root_resource.external_url = None
                root_resource.save()
                # Only the first root_resource is the root root_resource
                is_root = False
            asset.save(update_timestamps=False)
            if skip:
                continue
