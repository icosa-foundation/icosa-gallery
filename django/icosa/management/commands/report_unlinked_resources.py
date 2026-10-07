import csv
import posixpath

from django.core.management.base import BaseCommand
from django.db.models import Prefetch, Q
from icosa.models import Format, Resource
from icosa.models.format import url_relative_path
from icosa.models.resource import external_only_q

PRESENT = "present"
MISSING = "missing"
UNPLACEABLE = "outside root directory"


class Command(BaseCommand):
    help = """Report formats whose root resource is already stored locally but
    which still have externally-hosted resources (e.g. the
    model_(GLTFupdated).gltf roots from the Poly import).

    localize_external_formats links each such resource to the file of the
    same relative path alongside the root, and refuses the format if any is
    missing. This lists every resource with whether that file exists, so the
    missing ones can be fixed before localizing. Read-only.
    """

    def add_arguments(self, parser):
        parser.add_argument("--csv", help="Also write every resource checked to this CSV file")
        parser.add_argument("--all", action="store_true", help="List present resources too, not just problems")

    def handle(self, *args, **options):
        storage = Resource._meta.get_field("file").storage
        external = Resource.objects.filter(external_only_q())
        formats = (
            Format.objects.filter(Q(root_resource__file__gt="") & external_only_q("resource__"))
            .distinct()
            .select_related("asset", "root_resource")
            .prefetch_related(Prefetch("resource_set", queryset=external, to_attr="external_resources"))
            .order_by("pk")
        )

        rows = []
        blocked_formats = 0
        format_count = 0
        for format in formats.iterator(chunk_size=500):
            format_count += 1
            root = format.root_resource
            root_dir = posixpath.dirname(root.file.name)
            base_url = f"{root.external_url.rsplit('/', 1)[0]}/" if root.external_url else None
            blocked = False
            for resource in format.external_resources:
                rel = url_relative_path(resource.external_url, base_url)
                if rel is None:
                    status, path = UNPLACEABLE, ""
                else:
                    path = f"{root_dir}/{rel}"
                    status = PRESENT if storage.exists(path) else MISSING
                blocked = blocked or status != PRESENT
                row = [format.asset.url, format.pk, format.format_type, resource.pk, status, path, resource.external_url]
                rows.append(row)
                if status != PRESENT or options["all"]:
                    self.stdout.write(
                        f"{status}: asset {format.asset.url} format {format.pk} ({format.format_type}) "
                        f"resource {resource.pk} {path or resource.external_url}"
                    )
            blocked_formats += blocked

        if options["csv"]:
            with open(options["csv"], "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["asset_url", "format_id", "format_type", "resource_id", "status", "path", "external_url"])
                writer.writerows(rows)

        counts = {status: sum(1 for row in rows if row[4] == status) for status in (PRESENT, MISSING, UNPLACEABLE)}
        self.stdout.write(
            self.style.SUCCESS(
                f"{format_count} formats, {len(rows)} external resources: {counts[PRESENT]} present, "
                f"{counts[MISSING]} missing, {counts[UNPLACEABLE]} outside the root directory. "
                f"{blocked_formats} formats would be refused by localize_external_formats."
            )
        )
