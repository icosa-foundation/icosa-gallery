import json
import urllib

from django.core.management.base import BaseCommand
from django.db.models import Q

from django_project import settings
from icosa.models import (
    Asset,
    Format,
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

media_root = os.path.abspath(os.path.join(settings.BASE_DIR, settings.MEDIA_ROOT))


class Command(BaseCommand):

    help = "Copies preferred viewable format from remote to local storage"

    def check_gltf(self, gltf_path):

        if not gltf_path.endswith(".gltf"):
            print(f"Not a GLTF file extension: {gltf_path}")
            return {"is_valid": False}

        with open(gltf_path, "rb") as f:
            content = f.read()
            try:
                gltf_json = json.loads(content.decode("utf-8", errors="replace"))
            except Exception as e:
                print(f"Invalid content: {content[:10]}")
                return {"is_valid": False}

        is_v2 = not isinstance(gltf_json.get("buffers", None), dict)

        extensions = gltf_json.get("extensions", None)
        uses_techniques = (
                extensions is not None and
                extensions.get("GOOGLE_tilt_brush_techniques", None) is not None
        )

        return {
            "is_valid": True,
            "uses_techniques": uses_techniques,
            "is_v2": is_v2
        }

    def download_if_needed(self, resource, rel_path, forced):

        rel_path = os.path.join(resource.asset.url, rel_path)
        rel_path = rel_path.replace("/", "\\")
        rel_path = urllib.parse.unquote(rel_path)

        # TODO See later note about where this breaks the relative path calculation
        # There are relative paths that start with c:\ or similar
        # which will break os.path.join on Windows
        rel_path = rel_path.replace(":", "%3A")
        path = os.path.join(media_root, rel_path)
        url = resource.external_url
        if not url:
            raise Exception("No external URL")
        if os.path.exists(path) and not forced:
            print("Already downloaded", path)
        else:
            resource_dir = os.path.dirname(path)
            os.makedirs(resource_dir, exist_ok=True)
            print("Downloading", url, "to", path)
            try:
                response = session.get(url, allow_redirects=True)
            except Exception as e:
                print(f"Failed to download {url}: {e}")
                return None
            with open(path, "wb") as f:
                f.write(response.content)
        return path

    # Fix up the path and store it in the resource
    def finalize_resource(self, path, destination_resource):

        canonical_path = os.path.abspath(path)
        if not canonical_path.startswith(media_root):
            print(f"Invalid path: {canonical_path}")
            raise Exception(f"Invalid path: {canonical_path}")

        # TODO This is buggy for assets where we replaced drive letters with %3A earlier
        relative_path = canonical_path[len(media_root) + 1:]
        destination_resource.file = relative_path

        # Do we want to clear external_url?
        # root_resource.external_url = None

        print(f"Finalized path: {relative_path}")
        destination_resource.save()
        print(f"Finalized resource: {destination_resource.pk}")
        print(f"Finalized resource: {destination_resource.file.path}")

    # Deletes all files and directories for this asset
    # Except for the thumbnail.png
    def delete_all_files(self, asset_url):
        root = os.path.join(media_root, asset_url)
        for root_dir, dirs, files in os.walk(root, topdown=False):
            for name in files:
                if name == "thumbnail.png": continue
                path = os.path.join(root_dir, name)
                os.unlink(path)
            for name in dirs:
                path = os.path.join(root_dir, name)
                os.rmdir(path)


    def handle(self, *args, **options):

        for asset in Asset.objects.all():

            # Skip assets that are owned by stores with too many assets
            if asset.owner.displayname in [
                "Sora Cycling",
                "Verge Sport",
                "arman apelo",
                "Rovikov"
            ]:
                self.delete_all_files(asset.url)
                continue

            # Assume that the presence of a preferred viewer format means that we have already processed this asset
            preferred_qs = asset.format_set.filter(is_preferred_for_viewer=True)
            already_processed = preferred_qs.exists()

            if already_processed:
                print(f"Already Processed asset: {asset.url}")
                continue

            print(f"Processing asset: {asset.url}")
            nonstandard_preferred_format = False
            # Try the preferred viewer format first
            root_resource = asset._preferred_viewer_format["resource"]
            root_base_path, root_filename = root_resource.external_url.rsplit("/", 1)
            root_full_path = self.download_if_needed(root_resource, root_filename, forced=False)
            if root_full_path is None: continue
            gltf_status = self.check_gltf(root_full_path)

            print(gltf_status)

            if not gltf_status["is_valid"] or gltf_status["uses_techniques"]:
                nonstandard_preferred_format = True
                print("Trying alternate GLTF formats")
                os.unlink(root_full_path)
                # Try the one of the other GLTF formats
                unknown_gltf_q = Q(role=4) | Q(role=35)
                found_alternate = False
                for format_candidate in asset.format_set.filter(unknown_gltf_q):
                    root_resource = format_candidate.root_resource
                    root_base_path, root_filename = root_resource.external_url.rsplit("/", 1)
                    print(f"Trying {format_candidate.role} {root_base_path} // {root_filename}")
                    root_full_path = self.download_if_needed(root_resource, root_filename, forced=True)
                    if root_full_path is None:
                        print(f"Skipping failed download")
                        continue
                    gltf_status = self.check_gltf(root_full_path)
                    print(gltf_status)
                    if not gltf_status["is_valid"] or gltf_status["uses_techniques"]:
                        print(f"Skipping")
                        continue
                    else:
                        print(f"Found valid GLTF format: {format_candidate.role}")
                        found_alternate = True
                        break

                if not found_alternate:
                    print(f"No valid GLTF format found: {asset.url}")
                    print()
                    if os.path.exists(root_full_path):
                        os.unlink(root_full_path)
                    continue

            if nonstandard_preferred_format:
                print(f"Using alternate GLTF format: {format_candidate.role}")
            root_resource.format_type = gltf_status["is_v2"] if "GLTF2" else "GLTF1"
            self.finalize_resource(root_full_path, root_resource)

            # We have a valid root resource, now download the sub-resources
            root_format = Format.objects.get(root_resource=root_resource)
            resources = root_format.resource_set.all()
            for sub_resource in resources:
                sub_rel_path = sub_resource.external_url[len(root_base_path) + 1:]
                force_redownload = nonstandard_preferred_format and sub_rel_path.endswith(".bin")
                sub_full_path = self.download_if_needed(sub_resource, sub_rel_path, forced=force_redownload)
                if sub_full_path is None:
                    print(f"Skipping failed download")
                    continue
                self.finalize_resource(sub_full_path, sub_resource)

            for format in asset.format_set.all():
                format.is_preferred_for_viewer = format.root_resource == root_resource
                format.save()
            asset.save(update_timestamps=False)
            print(f"Finished processing asset: {asset.url}")
            print()