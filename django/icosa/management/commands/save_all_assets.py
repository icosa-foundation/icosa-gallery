from django.core.management.base import BaseCommand
from icosa.tasks import queue_save_all_assets, save_all_assets


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print logs to stdout",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Resume last killed batch",
        )
        parser.add_argument(
            "--background",
            action="store_true",
            help="Queues this task using Huey. --verbose has no effect here.",
        )

    def handle(self, *args, **options):
        resume = bool(options["resume"])
        verbose = bool(options["verbose"])
        if options["background"]:
            queue_save_all_assets(resume=resume)
        else:
            save_all_assets(
                resume=resume,
                verbose=verbose,
            )
