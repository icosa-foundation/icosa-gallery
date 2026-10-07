import json

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from icosa.models import Asset, Format
from icosa.models.resource import external_only_q
from icosa.tasks import localize_format, queue_localize_format


class Command(BaseCommand):
    help = """Queue Huey tasks that copy externally-hosted format files (e.g.
    on archive.org) into our own storage so they no longer depend on external
    URLs. Formats that still have external resources or archives are queued.

    Example:
        manage.py localize_external_formats \\
            --filter '{"owner__url": "poly", "visibility": "PUBLIC"}' \\
            --format-type GLTF2 --format-type OBJ --dry-run
    """

    def add_arguments(self, parser):
        assets = parser.add_argument_group("asset selection (combined with AND)")
        assets.add_argument(
            "--filter",
            help='JSON object of Asset lookups passed to .filter(), e.g. \'{"owner__url": "poly"}\'',
        )
        assets.add_argument(
            "--exclude",
            help="JSON object of Asset lookups passed to .exclude()",
        )
        assets.add_argument("--asset-id", type=int, action="append", dest="asset_ids", help="Repeatable")
        assets.add_argument("--asset-url", action="append", dest="asset_urls", help="Repeatable")
        assets.add_argument("--all-assets", action="store_true", help="Required if no other asset selection is given")

        formats = parser.add_argument_group("format selection (combined with OR)")
        formats.add_argument("--format-type", action="append", dest="format_types", help="e.g. GLTF2. Repeatable")
        formats.add_argument("--role", action="append", dest="roles", help="Repeatable")
        formats.add_argument(
            "--preferred-viewer",
            action="store_true",
            help="Formats marked is_preferred_for_gallery_viewer",
        )
        formats.add_argument(
            "--preferred-download",
            action="store_true",
            help="Formats marked is_preferred_for_download",
        )
        formats.add_argument("--all-formats", action="store_true", help="Every format of the selected assets")

        parser.add_argument("--limit", type=int, help="Queue at most this many formats")
        parser.add_argument("--dry-run", action="store_true", help="List what would be queued")
        parser.add_argument(
            "--foreground",
            action="store_true",
            help="Run in this process instead of queueing Huey tasks (useful for testing)",
        )

    def parse_lookups(self, value, name):
        try:
            lookups = json.loads(value)
        except json.JSONDecodeError as e:
            raise CommandError(f"--{name} is not valid JSON: {e}")
        if not isinstance(lookups, dict):
            raise CommandError(f"--{name} must be a JSON object")
        return lookups

    def get_assets(self, options):
        assets = Asset.objects.all()
        selected = False
        if options["filter"]:
            assets = assets.filter(**self.parse_lookups(options["filter"], "filter"))
            selected = True
        if options["exclude"]:
            assets = assets.exclude(**self.parse_lookups(options["exclude"], "exclude"))
            selected = True
        if options["asset_ids"]:
            assets = assets.filter(pk__in=options["asset_ids"])
            selected = True
        if options["asset_urls"]:
            assets = assets.filter(url__in=options["asset_urls"])
            selected = True
        if not selected and not options["all_assets"]:
            raise CommandError("Select assets with --filter/--exclude/--asset-id/--asset-url, or pass --all-assets.")
        return assets

    def get_format_q(self, options):
        q = Q()
        if options["format_types"]:
            q |= Q(format_type__in=options["format_types"])
        if options["roles"]:
            q |= Q(role__in=options["roles"])
        if options["preferred_viewer"]:
            q |= Q(is_preferred_for_gallery_viewer=True)
        if options["preferred_download"]:
            q |= Q(is_preferred_for_download=True)
        if not q and not options["all_formats"]:
            raise CommandError(
                "Select formats with --format-type/--role/--preferred-viewer/--preferred-download, or pass --all-formats."
            )
        return q

    def handle(self, *args, **options):
        assets = self.get_assets(options)
        formats = (
            Format.objects.filter(asset__in=assets)
            .filter(self.get_format_q(options))
            .filter(
                external_only_q("root_resource__")
                | external_only_q("resource__")
                | Q(zip_archive_url__gt="")
            )
            .distinct()
            .order_by("pk")
            .values_list("pk", "asset__url", "format_type")
        )
        if options["limit"]:
            formats = formats[: options["limit"]]

        count = 0
        for format_id, asset_url, format_type in formats.iterator():
            count += 1
            label = f"format {format_id} ({format_type}) of asset {asset_url}"
            if options["dry_run"]:
                self.stdout.write(f"Would localize {label}")
            elif options["foreground"]:
                try:
                    n = localize_format(format_id)
                    self.stdout.write(f"Localized {n} resources for {label}")
                except Exception as e:
                    self.stderr.write(f"Failed {label}: {e}")
            else:
                queue_localize_format(format_id)
                self.stdout.write(f"Queued {label}")

        verb = "Would queue" if options["dry_run"] else "Processed" if options["foreground"] else "Queued"
        self.stdout.write(self.style.SUCCESS(f"{verb} {count} formats."))
