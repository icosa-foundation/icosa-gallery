import json

from django.core.management.base import BaseCommand
from django.db.models import Q
from icosa.models import Asset, Format
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


def handle_blocks_preferred_format(asset):
    # TODO(james): This handler is specific to data collected from blocks.
    # We should use this logic to populate the database with the correct
    # information. But for now, we don't know this method is 100% correct,
    # so I'm leaving this here.
    if not asset.has_gltf2:
        # There are some issues with displaying GLTF1 files from Blocks
        # so we have to return an OBJ and its associated MTL.
        obj_format = asset.format_set.filter(format_type="OBJ", root_resource__isnull=False).first()
        obj_resource = obj_format.root_resource
        mtl_resource = obj_format.resource_set.first()

        if not obj_resource:
            # TODO: If we fail to find an obj, do we want to handle this
            # with an error?
            return None
        return {
            "format": obj_format,
            "url": obj_resource.internal_url_or_none,
            "materialUrl": mtl_resource.url,
            "resource": obj_resource,
        }
    # We have a gltf2, but we must currently return the suffixed version we
    # have in storage; the non-suffixed version currently does not work.
    blocks_format = asset.format_set.filter(format_type="GLTF2").first()
    blocks_resource = None
    if blocks_format is not None:
        blocks_resource = blocks_format.root_resource
    if blocks_format is None or blocks_resource is None:
        # TODO: If we fail to find a gltf2, do we want to handle this with
        # an error?
        return None
    filename = blocks_resource.url
    if filename is None:
        return None
    filename = f"poly/{asset.url}/{filename.split('/')[-1]}"
    # NUMBER_1 When we hit this block, we need to save the suffix to the file field
    url = f"{suffix(filename)}"
    return {"format": blocks_format, "url": url, "resource": blocks_resource, "is_blocks_to_suffix": True}


def preferred_viewer_format(asset):
    if asset.preferred_viewer_format_override is not None:
        format = asset.preferred_viewer_format_override
        root_resource = format.root_resource
        return {"format": format, "url": root_resource.internal_url_or_none, "resource": root_resource}

    if asset.has_blocks:
        return handle_blocks_preferred_format(asset)

    # Return early if we can grab a Polygone resource first
    polygone_gltf = None
    format = asset.format_set.filter(
        role__in=["POLYGONE_GLB_FORMAT", "POLYGONE_GLTF_FORMAT"], root_resource__isnull=False
    ).first()
    if format:
        polygone_gltf = format.root_resource

    if polygone_gltf:
        return {"format": format, "url": polygone_gltf.internal_url_or_none, "resource": polygone_gltf}

    # Return early with either of the role-based formats we care about.
    updated_gltf = None
    format = asset.format_set.filter(root_resource__isnull=False, role=30).first()
    if format:
        updated_gltf = format.root_resource

    if updated_gltf:
        return {"format": format, "url": updated_gltf.internal_url_or_none, "resource": updated_gltf}

    original_gltf = None
    format = asset.format_set.filter(root_resource__isnull=False, role=12).first()
    if format:
        original_gltf = format.root_resource

    if original_gltf:
        return {"format": format, "url": original_gltf.internal_url_or_none, "resource": original_gltf}

    # If we didn't get any role-based formats, find the remaining formats
    # we care about and choose the "best" one of those.
    formats = {}
    for format in asset.format_set.all():
        root = format.root_resource
        if root is None:
            # We can't get a url for a Format without a root resource.
            # This is an exceptional circumstance.
            return None
        formats[format.format_type] = {"format": format, "url": root.internal_url_or_none, "resource": root}
    # GLB is our primary preferred format;
    if "GLB" in formats.keys():
        return formats["GLB"]
    # GLTF2 is the next best option;
    if "GLTF2" in formats.keys():
        return formats["GLTF2"]
    # GLTF1, if we must.
    if "GLTF1" in formats.keys():
        return formats["GLTF1"]
    # Last chance, OBJ
    if "OBJ" in formats.keys():
        return formats["OBJ"]
    return None


class Command(BaseCommand):
    help = """Exports data for writing to the database based on runtime behavior. Bakes preferred format and downloadable formats."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of asset ids to operate on. If blank, will operate on all assets.",
        )

    def handle(self, *args, **options):
        # These two lists are for downloads:
        formats_to_create = []  # These formats comprise runtime data that we are instead adding to the database as new, unhidden formats.
        formats_to_hide = []  # These formats are not eligible for download.

        # These two lists are for preferred formats:
        format_resources_to_suffix = {}  # Blocks GLTF2 resources need to have the suffix added. It's more efficient to change the url than to create a whole new format just for this purpose.
        formats_to_prefer = []  # These are the ones we will mark as preferred.

        asset_ids = options.get("asset_ids")
        if asset_ids:
            assets = Asset.objects.filter(id__in=asset_ids)
        else:
            assets = Asset.objects.all()
        # assets = Asset.objects.filter(id=586142320819176293)
        print(f"todo: {assets.count()} assets.")
        for i, asset in enumerate(assets):
            if i % 1000 == 0:
                print(f"done {i}")

            # ==================================
            # Compute data for preferred formats
            # ==================================

            p_format = preferred_viewer_format(asset)
            if p_format is None:
                continue
            if p_format["url"] is None:
                continue
            formats_to_prefer.append(p_format["format"].id)
            if p_format.get("is_blocks_to_suffix", False) is True:
                format_resources_to_suffix.update({p_format["resource"].id: p_format["url"]})

            # ==========================
            # Compute data for downloads
            # ==========================

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
                    # files work correctly.
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
                        "file": f"{suffix(root_resource.file.name)}",
                    }
                    new_format_data["root_resource"] = root_resource_data
                    new_format_data["resources"] = [
                        {
                            "asset": x.asset.id,
                            "format": x.format.id,
                            "contenttype": x.contenttype,
                            "file": f"{suffix(x.file.name)}",
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
                            "file": f"{suffix(override_format_root.file.name)}",
                        }
                        new_format_data["root_resource"] = root_resource_data
                        new_format_data["resources"] = [
                            {
                                "asset": x.asset.id,
                                "format": x.format.id,
                                "contenttype": x.contenttype,
                                "file": f"{suffix(x.file.name)}",
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

        with open("format-resources-to-suffix.json", "w", encoding="utf-8") as f:
            json.dump(format_resources_to_suffix, f, ensure_ascii=False)

        with open("formats-to-prefer.json", "w", encoding="utf-8") as f:
            json.dump(formats_to_prefer, f, ensure_ascii=False)
