import json

from django.core.management.base import BaseCommand
from django.db.models import Q
from icosa.models import Asset, Format, Resource
from icosa.models.common import STORAGE_PREFIX
from icosa.models.helpers import suffix

STORAGE_ROOT = "https://f005.backblazeb2.com/file/icosa-gallery/"

ND_WEB_UI_DOWNLOAD_COMPATIBLE_ROLES = [
    "ORIGINAL_FBX_FORMAT",
    "ORIGINAL_OBJ_FORMAT",
    "ORIGINAL_TRIANGULATED_OBJ_FORMAT",
    "USD_FORMAT",
    "GLB_FORMAT",
    "USDZ_FORMAT",
    "UPDATED_GLTF_FORMAT",
    "USER_SUPPLIED_GLTF",
]

WEB_UI_DOWNLOAD_COMPATIBLE_ROLES = ND_WEB_UI_DOWNLOAD_COMPATIBLE_ROLES + [
    # Assuming here that a Tilt-native gltf can be considered a "source file"
    # and so not eligible for download and reuse.
    "TILT_NATIVE_GLTF",
    "TILT_FORMAT",
    "BLOCKS_FORMAT",
]


def asset_inferred_downloads(asset, user=None):
    # Originally, Google Poly made these roles available for download:
    # - Original FBX File
    # - Original OBJ File
    # - GLB File
    # - Original Triangulated OBJ File
    # - Original glTF File
    # - USDZ File
    # - Updated glTF File

    if asset.license in ["CREATIVE_COMMONS_BY_ND_3_0", "CREATIVE_COMMONS_BY_ND_4_0"]:
        # We don't allow downoad of source files for ND-licensed work.
        dl_formats = asset.format_set.filter(role__in=ND_WEB_UI_DOWNLOAD_COMPATIBLE_ROLES)
    else:
        dl_formats = asset.format_set.filter(role__in=WEB_UI_DOWNLOAD_COMPATIBLE_ROLES)
    return dl_formats


def format_process_download_resources(format):
    # Query all resources which have either an external url or a
    # file. Ignoring resources which have neither.
    query = Q(external_url__isnull=False) & ~Q(external_url="")
    query |= Q(file__isnull=False)
    resources = format.get_all_resources(query)

    # If there is more than one resource, this means we need to
    # create a zip file of it on the client. We can only do this
    # if either:
    # a) the resource is hosted by Django
    # b) all the resources we need to zip are accessible because
    #    they are on the CORS allow list.
    # The second criteria is met if the resource's remote host is
    # in the EXTERNAL_MEDIA_CORS_ALLOW_LIST setting in constance.
    if len(resources) > 1:
        resource_data = get_resource_data_by_role(
            format,
            resources,
            format.role,
        )

    return (format.type.lower(), resource_data)


class Command(BaseCommand):
    help = """Extracts format json into concrete models and converts to poly
    format."""

    def handle(self, *args, **options):
        formats_to_create = []
        formats_to_hide = []

        assets = Asset.objects.all()
        print(f"todo: {assets.count()} assets.")
        for i, asset in enumerate(assets):
            if i % 1000 == 0:
                print(f"done {i}")
            downloadable_formats = asset_inferred_downloads(asset, None)
            asset_formats_to_hide = list(
                Format.objects.filter(asset=asset)
                .exclude(id__in=[x.id for x in downloadable_formats])
                .values_list("id", flat=True)
            )

            formats_to_hide += asset_formats_to_hide

            for format in downloadable_formats:
                if format.zip_archive_url:
                    # These formats will all be downloadable.
                    continue

                query = Q(external_url__isnull=False) & ~Q(external_url="")
                query |= Q(file__isnull=False)
                resources = format.get_all_resources(query)

                if len(resources) == 1:
                    # These formats will all be downloadable.
                    continue

                # This is the case where we have > 1 resource in the format so
                # need to decide what to do.
                if format.role == "POLYGONE_GLTF_FORMAT":
                    # If we hit this branch, we are not clear on if all gltf
                    # files work correctly. Try both the original data we
                    # ingested and include the suffixed data which attempts to
                    # fix any errors. Add some supporting text to make it clear
                    # to the user this is the case.
                    #
                    # We need to create a new format with the suffixed
                    # resources.
                    #
                    # We also need to keep this one active, as it might still
                    # work.
                    #
                    # Create a naive copy of the format's data then assign
                    # resources.
                    new_format_data = {
                        "asset": asset.id,
                        "format_type": format.format_type,
                        "zip_archive_url": format.zip_archive_url,
                        "triangle_count": format.triangle_count,
                        "lod_hint": format.lod_hint,
                        "role": format.role,
                        "is_preferred_for_gallery_viewer": format.is_preferred_for_gallery_viewer,
                        "hide_from_downloads": False,
                    }

                    root_resource = format.root_resource
                    if root_resource is None:
                        continue  # We don't have the information we need to create a complete format.
                        if not root_resource.file:
                            continue  # We don't have the information we need to create a complete format.
                    root_resource_data = {
                        "asset": root_resource.asset.id,
                        "format": None,
                        "contenttype": root_resource.contenttype,
                        "file": f"{STORAGE_PREFIX}{suffix(root_resource.file.name)}",
                    }
                    new_format_data["root_resource"] = root_resource_data
                    new_format_data["resources"] = [
                        {
                            "asset": x.asset.id,
                            "format": x.format.id,
                            "contenttype": x.contenttype,
                            "file": f"{STORAGE_PREFIX}{suffix(x.file.name)}",
                        }
                        for x in resources
                        if x.file
                    ]

                    formats_to_create.append(new_format_data)
                else:
                    resource_data = format.get_resource_data(resources)
                if not resource_data and format.role == "UPDATED_GLTF_FORMAT":
                    # If we hit this branch, we have a format which doesn't
                    # have an archive url, but also doesn't have local files.
                    # At time of writing, we can't create a zip on the client
                    # from the archive.org urls because of CORS. So compile a
                    # list of files as if the role was 1003 using our suffixed
                    # upload.
                    #
                    # We also need to hide the original format from downloads.
                    formats_to_hide.append(format.id)

                    try:
                        override_format = format.asset.format_set.get(role="POLYGONE_GLTF_FORMAT")
                        override_resources = list(override_format.resource_set.all())
                        override_format_root = override_format.root_resource

                        # Create a naive copy of the format's data then assign
                        # resources.
                        new_format_data = {
                            "asset": asset.id,
                            "format_type": override_format.format_type,
                            "zip_archive_url": override_format.zip_archive_url,
                            "triangle_count": override_format.triangle_count,
                            "lod_hint": override_format.lod_hint,
                            "role": override_format.role,
                            "is_preferred_for_gallery_viewer": override_format.is_preferred_for_gallery_viewer,
                            "hide_from_downloads": False,
                        }

                        if override_format_root is None:
                            continue  # We don't have the information we need to create a complete format.
                            if not override_format_root.file:
                                continue  # We don't have the information we need to create a complete format.

                        root_resource_data = {
                            "asset": override_format_root.asset.id,
                            "format": None,
                            "contenttype": override_format_root.contenttype,
                            "file": f"{STORAGE_PREFIX}{suffix(override_format_root.file.name)}",
                        }
                        new_format_data["root_resource"] = root_resource_data
                        new_format_data["resources"] = [
                            {
                                "asset": x.asset.id,
                                "format": x.format.id,
                                "contenttype": x.contenttype,
                                "file": f"{STORAGE_PREFIX}{suffix(x.file.name)}",
                            }
                            for x in override_resources
                            if x.file
                        ]

                        formats_to_create.append(new_format_data)
                    except (
                        Format.DoesNotExist,
                        Format.MultipleObjectsReturned,
                    ):
                        pass

        with open("formats-to-hide.json", "w", encoding="utf-8") as f:
            json.dump(formats_to_hide, f, ensure_ascii=False)

        with open("formats-to-create.json", "w") as f:
            json.dump(formats_to_create, f, ensure_ascii=False, indent=4)
