from django.core.management.base import BaseCommand
from django.db.models import Q
from icosa.models import Asset, Format
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


def get_resource_data_by_role(format, resources, role):
    if format.role == "POLYGONE_GLTF_FORMAT":
        # If we hit this branch, we are not clear on if all gltf files work
        # correctly. Try both the original data we ingested and include
        # the suffixed data which attempts to fix any errors. Add some
        # supporting text to make it clear to the user this is the case.
        resource_data = {
            "files_to_zip": [f"{STORAGE_PREFIX}{x.file.name}" for x in resources if x.file],
            "files_to_zip_with_suffix": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in resources if x.file],
            "supporting_text": "Try the alternative download if the original doesn't work for you. We're working to fix this.",
        }
    else:
        resource_data = format.get_resource_data(resources)
    if not resource_data and format.role == "UPDATED_GLTF_FORMAT":
        # If we hit this branch, we have a format which doesn't
        # have an archive url, but also doesn't have local files.
        # At time of writing, we can't create a zip on the client
        # from the archive.org urls because of CORS. So compile a
        # list of files as if the role was 1003 using our suffixed
        # upload.
        try:
            override_format = format.asset.format_set.get(role="POLYGONE_GLTF_FORMAT")
            override_resources = list(override_format.resource_set.all())
            override_format_root = override_format.root_resource
            if override_format_root is not None:
                if override_format_root.file or override_format_root.external_url:
                    override_resources.append(override_format_root)
            resource_data = {
                "files_to_zip": [f"{STORAGE_PREFIX}{suffix(x.file.name)}" for x in override_resources if x.file],
            }
        except (
            Format.DoesNotExist,
            Format.MultipleObjectsReturned,
        ):
            resource_data = {}
    return resource_data


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
        resources_to_hide = []
        asset_viewer_data = {}

        assets = Asset.objects.all()
        print(f"todo: {assets.count()} assets.")
        for i, asset in enumerate(assets):
            if i % 1000:
                print(f"done {i}")
            downloadable_formats = asset_inferred_downloads(asset, None)
            asset_formats_to_hide = list(
                Format.objects.filter(asset=asset)
                .exclude(id__in=[x.id for x in downloadable_formats])
                .values_list("id", flat=True)
            )
            continue
            formats_to_hide += asset_formats_to_hide

            for format in downloadable_formats:
                (format_name, resource_data) = format_process_download_resources(format)
