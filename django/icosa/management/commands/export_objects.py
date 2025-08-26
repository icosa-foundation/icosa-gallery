import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from icosa.import_export.exporter import do_export

User = get_user_model()


def handle_file(file_path: str) -> list:
    ids = []
    try:
        with open(file_path, "r") as f:
            ids = json.load(f)
            if type(ids) is not list:
                raise CommandError(f"No list of ids found in {file_path}.")
            if not all(isinstance(item, int) for item in ids):
                raise CommandError(f"File, {file_path} must contain only integers.")
    except Exception:
        raise CommandError(f"Error reading file: {file_path}.")
    return ids


def parse_option_prefix(arg_name: str, options: dict) -> list:
    ids = []
    ids_arg = options.get(arg_name, None)
    ids_file = options.get(f"{arg_name}_from_file", None)
    if ids_arg is not None:
        ids = ids_arg
    else:
        ids = handle_file(ids_file)
    return ids


def parse_options(options):
    asset_ids = parse_option_prefix("asset_ids")
    owner_ids = parse_option_prefix("owner_ids")
    user_ids = parse_option_prefix("user_ids")

    return (
        asset_ids,
        owner_ids,
        user_ids,
    )


class Command(BaseCommand):
    help = """Exports data for import into another instance of Icosa Gallery."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of Asset ids to export. If blank, will export all Assets. Overrides this option's `-from-file` variant.",
        )
        parser.add_argument(
            "--owner-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of AssetOwner ids to export. If blank, will export all assets. Overrides this option's `-from-file` variant.",
        )
        parser.add_argument(
            "--user-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of User ids to export. If blank, will export all assets. Overrides this option's `-from-file` variant.",
        )
        parser.add_argument(
            "--asset-ids-from-file",
            default=None,
            type=str,
            help="Path to a file that contains a json list of Asset ids to export. If blank, will export all Assets.",
        )
        parser.add_argument(
            "--owner-ids-from-file",
            default=None,
            type=str,
            help="Path to a file that contains a json list of AssetOwner ids to export. If blank, will export all assets.",
        )
        parser.add_argument(
            "--user-ids-from-file",
            default=None,
            type=str,
            help="Path to a file that contains a json list of User ids to export. If blank, will export all assets.",
        )

    def handle(self, *args, **options):
        asset_ids, owner_ids, user_ids = parse_options(options)

        do_export(
            asset_ids=asset_ids,
            owner_ids=owner_ids,
            user_ids=user_ids,
        )
