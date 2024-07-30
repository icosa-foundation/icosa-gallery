from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    help = "Sets site name and domain"

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            action="store",
            help="The site's name, e.g. Example Site",
            required=True,
        )
        parser.add_argument(
            "--domain",
            action="store",
            help="The site's domain with no scheme, e.g. www.example.com",
            required=True,
        )

    def handle(self, *args, **options):
        defaults = {
            "name": options["name"].strip(),
            "domain": options["domain"].strip(),
        }
        site, created = Site.objects.update_or_create(
            pk=1,
            defaults=defaults,
            create_defaults=defaults,
        )
        print(
            f"Updated the site with name: {site.name}, domain: {site.domain}"
        )
