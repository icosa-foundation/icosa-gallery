from django.core.management.base import BaseCommand
from django.db.models import Count

from icosa.models import Asset


class Command(BaseCommand):
    help = (
        "Delete assets that have no viewable formats. "
        "This cleans up orphaned assets that were created but never successfully imported."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting anything",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip confirmation prompt",
        )
        parser.add_argument(
            "--source",
            dest="source",
            default=None,
            help="Only delete assets from a specific import source (e.g., 'sketchfab')",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        skip_confirm = options.get("yes", False)
        source = options.get("source")

        # Find assets with no formats
        assets_query = Asset.objects.annotate(
            format_count=Count("format_set")
        ).filter(format_count=0)

        # Filter by source if specified
        if source:
            assets_query = assets_query.filter(imported_from=source)

        assets = list(assets_query)
        count = len(assets)

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No assets found without formats."))
            return

        # Show what will be deleted
        self.stdout.write(f"\nFound {count} asset(s) without formats:")
        if options.get("verbosity", 1) >= 2:
            for asset in assets[:10]:  # Show first 10
                self.stdout.write(f"  - {asset.url}: {asset.name} (source: {asset.imported_from})")
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")

        # Source breakdown
        if options.get("verbosity", 1) >= 1:
            sources = {}
            for asset in assets:
                source_name = asset.imported_from or "(no source)"
                sources[source_name] = sources.get(source_name, 0) + 1
            self.stdout.write("\nBreakdown by source:")
            for source_name, source_count in sorted(sources.items()):
                self.stdout.write(f"  {source_name}: {source_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\n[DRY RUN] Would delete {count} asset(s). Run without --dry-run to actually delete.")
            )
            return

        # Confirmation
        if not skip_confirm:
            self.stdout.write(
                self.style.WARNING(f"\nThis will permanently delete {count} asset(s) from the database.")
            )
            confirm = input("Are you sure you want to continue? [y/N]: ")
            if confirm.lower() not in ["y", "yes"]:
                self.stdout.write("Cancelled.")
                return

        # Delete assets
        deleted_count = 0
        for asset in assets:
            try:
                asset_url = asset.url
                asset.delete()
                deleted_count += 1
                if options.get("verbosity", 1) >= 2:
                    self.stdout.write(f"Deleted: {asset_url}")
            except Exception as exc:
                self.stderr.write(f"Error deleting {asset.url}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(f"Successfully deleted {deleted_count} out of {count} asset(s).")
        )
