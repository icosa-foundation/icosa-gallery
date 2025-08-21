from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from icosa.import_export.exporter import do_export

User = get_user_model()


class Command(BaseCommand):
    help = """Exports data for import into another instance of Icosa Gallery."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--asset-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of Asset ids to export. If blank, will export all Assets. Use in conjunction with --owner-ids or --user-ids to further limit exported Assets.",
        )
        parser.add_argument(
            "--owner-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of AssetOwner ids whose Assets you wish to export. If blank, will export all assets. Use in conjunction with --user-ids or --asset-ids to further limit exported Assets.",
        )
        parser.add_argument(
            "--user-ids",
            nargs="*",
            default=[],
            type=int,
            help="Space-separated list of User ids to find s you wish to export. If blank, will export all assets. Use in conjunction with --asset-ids or --owner-ids to further limit exported Assets.",
        )

    def handle(self, *args, **options):
        asset_ids = options.get("asset_ids", [])
        owner_ids = options.get("owner_ids", [])
        user_ids = options.get("user_ids", [])

        do_export(
            asset_ids=asset_ids,
            owner_ids=owner_ids,
            user_ids=user_ids,
        )
