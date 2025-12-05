from django.core.management.base import BaseCommand  # , CommandError
from icosa.import_export.importer import do_import


class Command(BaseCommand):
    help = """Exports data for import into another instance of Icosa Gallery."""

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            help="The file name to import from.",
        )

    def handle(self, *args, **options):
        file_name = options["file"]
        do_import(file_name)
        # try:
        #     do_import(file_name)
        # except Exception as e:
        #     raise CommandError(e)
