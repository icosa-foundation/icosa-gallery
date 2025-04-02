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

            diff = []

            if icosa_asset.name != poly_asset.name:
                diff.append(f"Name: {icosa_asset.name} != {poly_asset.name}")

            idesc = icosa_asset.description if icosa_asset.description else ""
            pdesc = poly_asset.description if poly_asset.description else ""
            if idesc != pdesc:
                diff.append(f"Description: {len(idesc)} != {len(pdesc)}")

            if icosa_asset.visibility != poly_asset.visibility:
                diff.append(f"Visibility: {icosa_asset.visibility} != {poly_asset.visibility}")

            if diff:
                print(f"{icosa_asset.url} :: {poly_asset.url}")
                print("\n".join(diff))
                print("----------------------------------------")

        # print()
        # print()
        # print()
        # for owner_match in owner_matches:
        #     icosa_owner, poly_owner = owner_match
        #     print(f"{icosa_owner.displayname} :: {poly_owner.displayname}")