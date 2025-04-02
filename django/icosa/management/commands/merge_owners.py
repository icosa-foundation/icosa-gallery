from django.core.management import BaseCommand
from icosa.models import Asset


class Command(BaseCommand):

    def handle(self, *args, **options):

        icosa_assets = Asset.objects.filter(imported_from=None)

        owner_matches = set()

        for icosa_asset in icosa_assets:
            if not icosa_asset.polydata: continue
            poly_url = icosa_asset.polydata['name'].split('/')[-1]
            poly_asset = Asset.objects.filter(url=poly_url).first()
            if not poly_asset: continue
            owner_match = (icosa_asset.owner, poly_asset.owner)
            owner_matches.add(owner_match)
            print(icosa_asset.name, poly_asset.name)
        print()
        for owner_match in owner_matches:
            icosa_owner, poly_owner = owner_match
            print(icosa_owner.displayname, poly_owner.displayname)