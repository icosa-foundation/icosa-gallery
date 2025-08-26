import datetime
import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from icosa.models import Format

ROLE_MAP = {
    1: "ORIGINAL_OBJ_FORMAT",
    2: "TILT_FORMAT",
    4: "UNKNOWN_GLTF_FORMAT_A",
    6: "ORIGINAL_FBX_FORMAT",
    7: "BLOCKS_FORMAT",
    8: "USD_FORMAT",
    11: "HTML_FORMAT",
    12: "ORIGINAL_GLTF_FORMAT",
    13: "TOUR_CREATOR_EXPERIENCE",
    15: "JSON_FORMAT",
    16: "LULLMODEL_FORMAT",
    17: "SAND_FORMAT_A",
    18: "GLB_FORMAT",
    19: "SAND_FORMAT_B",
    20: "SANDC_FORMAT",
    21: "PB_FORMAT",
    22: "UNKNOWN_GLTF_FORMAT_B",
    24: "ORIGINAL_TRIANGULATED_OBJ_FORMAT",
    25: "JPG_BUGGY",
    26: "USDZ_FORMAT",
    30: "UPDATED_GLTF_FORMAT",
    32: "EDITOR_SETTINGS_PB_FORMAT",
    35: "UNKNOWN_GLTF_FORMAT_C",
    36: "UNKNOWN_GLB_FORMAT_A",
    38: "UNKNOWN_GLB_FORMAT_B",
    39: "TILT_NATIVE_GLTF",
    40: "USER_SUPPLIED_GLTF",
    1000: "POLYGONE_TILT_FORMAT",
    1001: "POLYGONE_BLOCKS_FORMAT",
    1002: "POLYGONE_GLB_FORMAT",
    1003: "POLYGONE_GLTF_FORMAT",
    1004: "POLYGONE_OBJ_FORMAT",
    1005: "POLYGONE_FBX_FORMAT",
}

# ROLE_MAP_INVERSE = {v: k for k, v in ROLE_MAP.items()}


class Command(BaseCommand):
    help = """Converts format roles from integers to strings."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of asset ids to operate on. If blank, will operate on all assets.",
        )
        parser.add_argument(
            "--asset-ids-from-file",
            default=None,
            type=str,
            help="Path to a file that contains a json list of Asset ids to operate on. If blank, will operate on all Assets.",
        )
        parser.add_argument(
            "--exclude",
            action="store_true",
            help="With this flag present, any id lists supplied via arguments or files will be treated as ids to exclude. Applies globally to all other arguments.",
        )

    def handle(self, *args, **options):
        print("started ", datetime.datetime.now())

        asset_ids_arg = options.get("asset_ids")
        asset_ids_from_file = options.get("asset_ids_from_file")
        exclude_flag = bool(options.get("exclude"))

        q = Q(role__isnull=False)

        if asset_ids_arg:
            asset_ids = asset_ids_arg
        elif asset_ids_from_file:
            ids_from_file = []
            with open(asset_ids_from_file, "r") as f:
                ids_from_file = json.load(f)
                if type(ids_from_file) is not list:
                    raise CommandError(f"No list of ids found in {asset_ids_from_file}.")
                if not all(isinstance(item, int) for item in ids_from_file):
                    raise CommandError(f"File, {asset_ids_from_file} must contain only integers.")
            asset_ids = ids_from_file

        if exclude_flag:
            q &= ~Q(asset__id__in=asset_ids)
        else:
            q &= Q(asset__id__in=asset_ids)

        formats = Format.objects.filter(q).exclude(role="")
        for format in formats.iterator(chunk_size=1000):
            try:
                role = int(format.role)
                format.role = ROLE_MAP[role]
            except ValueError:
                pass
            role = format.role
            if role == "ORIGINAL_TRIANGULATED_OBJ_FORMAT":
                format.format_type = "OBJ"
            elif role == "ORIGINAL_OBJ_FORMAT":
                format.format_type = "OBJ_NGON"
            elif role == "POLYGONE_OBJ_FORMAT":
                # We are working on the assumption that POLYGONE formats are
                # never triangulated. This is up for debate later.
                format.format_type = "OBJ_NGON"
            format.format_type
            format.save()
        print("finished", datetime.datetime.now())
