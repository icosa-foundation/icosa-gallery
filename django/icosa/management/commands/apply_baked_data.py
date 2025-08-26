import json

from django.core.management.base import BaseCommand
from icosa.models import Asset, Format, FormatRoleLabel, Resource

DOWNLOADABLE_FORMAT_NAMES = {
    "ORIGINAL_OBJ_FORMAT": "obj",
    "TILT_FORMAT": "native tilt",
    "UNKNOWN_GLTF_FORMAT_A": "unknown gltf a",
    "ORIGINAL_FBX_FORMAT": "original fbx",
    "BLOCKS_FORMAT": "native blocks",
    "USD_FORMAT": "usd",
    "HTML_FORMAT": "html",
    "ORIGINAL_GLTF_FORMAT": "original gltf",
    "TOUR_CREATOR_EXPERIENCE": "tour creator experience",
    "JSON_FORMAT": "json",
    "LULLMODEL_FORMAT": "lullmodel",
    "SAND_FORMAT_A": "sand a",
    "GLB_FORMAT": "glb",
    "SAND_FORMAT_B": "sand b",
    "SANDC_FORMAT": "sandc",
    "PB_FORMAT": "pb",
    "UNKNOWN_GLTF_FORMAT_B": "unknown gltf b",
    "ORIGINAL_TRIANGULATED_OBJ_FORMAT": "triangulated obj",
    "JPG_BUGGY": "jpg buggy",
    "USDZ_FORMAT": "usdz",
    "UPDATED_GLTF_FORMAT": "gltf",
    "EDITOR_SETTINGS_PB_FORMAT": "editor settings pb",
    "UNKNOWN_GLTF_FORMAT_C": "unknown gltf c",
    "UNKNOWN_GLB_FORMAT_A": "unknown glb a",
    "UNKNOWN_GLB_FORMAT_B": "unknown glb b",
    "TILT_NATIVE_GLTF": "tilt native gltf",
    "USER_SUPPLIED_GLTF": "user supplied gltf",
    "POLYGONE_TILT_FORMAT": "polygone tilt",
    "POLYGONE_BLOCKS_FORMAT": "polygone blocks",
    "POLYGONE_GLB_FORMAT": "polygone glb",
    "POLYGONE_GLTF_FORMAT": "polygone gltf",
    "POLYGONE_OBJ_FORMAT": "polygone obj",
    "POLYGONE_FBX_FORMAT": "polygone fbx",
}


class Command(BaseCommand):
    help = """Extracts format json into concrete models and converts to poly
    format."""

    def handle(self, *args, **options):
        formats_to_prefer = json.load(open("formats-to-prefer.json"))
        formats_to_hide = json.load(open("formats-to-hide.json"))
        format_resources_to_suffix = json.load(open("format-resources-to-suffix.json"))
        formats_to_create = json.load(open("formats-to-create.json"))

        print("Updating preferred formats...")
        # Calling `update` on this queryset would result in too high memory usage.
        for format in Format.objects.filter(id__in=formats_to_prefer).iterator(chunk_size=1000):
            format.is_preferred_for_gallery_viewer = True
            format.save()

        print("Updating formats to hide from download...")
        # Calling `update` on this queryset would result in too high memory usage.
        for format in Format.objects.filter(id__in=formats_to_hide).iterator(chunk_size=1000):
            format.hide_from_downloads = True
            format.save()

        print("Suffixing resource urls...")
        for id, url in format_resources_to_suffix.items():
            resource = Resource.objects.get(id=id)
            resource.file = url
            resource.save()

        print("Creating formats for download...")
        for f in formats_to_create:
            asset = Asset.objects.get(id=f["asset"])

            format_data = {
                "asset": asset,
                "format_type": f["format_type"],
                "zip_archive_url": f["zip_archive_url"],
                "triangle_count": f["triangle_count"],
                "lod_hint": f["lod_hint"],
                "role": f["role"],
                "is_preferred_for_gallery_viewer": f["is_preferred_for_gallery_viewer"],
                "hide_from_downloads": f["hide_from_downloads"],
            }
            format = Format.objects.create(**format_data)

            rr = f["root_resource"]
            root_resource_data = {
                "asset": asset,
                "file": rr["file"],
                "format": format,
                "contenttype": rr["contenttype"],
            }
            root_resource = Resource.objects.create(**root_resource_data)
            format.add_root_resource(root_resource)

            for r in f["resources"]:
                resource_data = {
                    "asset": asset,
                    "file": r["file"],
                    "format": format,
                    "contenttype": r["contenttype"],
                }
                Resource.objects.create(**resource_data)

        print("Creating role labels...")
        role_texts = set()
        for f in Format.objects.filter(role__isnull=False):
            role_texts.add(f.role)
        for t in role_texts:
            label = DOWNLOADABLE_FORMAT_NAMES.get(t)
            role_label, _ = FormatRoleLabel.objects.get_or_create(role_text=t, defaults={"label": label})
