from django.core.cache import cache
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    help = """Clears out Django's page cache"""

    def handle(self, *args, **options):
        cache.clear()
