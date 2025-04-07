from django.core.management import BaseCommand
from icosa.models import Asset


class Command(BaseCommand):
    def handle(self, *args, **options):
        icosa_assets = Asset.objects.filter(imported_from=None)

        owner_matches = set()
        asset_matches = {}

        for icosa_asset in icosa_assets:
            if not icosa_asset.polydata:
                continue
            poly_url = icosa_asset.polydata["name"].split("/")[-1]
            poly_asset = Asset.objects.filter(url=poly_url).first()
            if not poly_asset:
                continue
            owner_match = (icosa_asset.owner, poly_asset.owner)
            owner_matches.add(owner_match)
            asset_matches[icosa_asset.owner] = (icosa_asset, poly_asset)

        # 1308 have become PRIVATE from PUBLIC
        # private was the default so the 1308 were people doing nothing except importing.
        # I propose we respect deliberate changes. i.e. we ignore the 1308
        # Copy over name and description changes from the icosa version and then delete the icosa version to remove duplicates

        for owners in owner_matches:
            icosa_owner, poly_owner = owners

            # TODO
            # Merge poly_owner assets into icosa_owner
            for poly_asset in poly_owner.assets.all():
                poly_asset.owner = icosa_owner
                poly_asset.save()

            for asset in asset_matches[icosa_owner]:
                icosa_asset, poly_asset = asset
                icosa_owner.refresh_from_db()
                poly_owner.refresh_from_db()

                if icosa_asset.visibility == PRIVATE:
                    # Most likely the user never changed the default visibility
                    pass
                else:
                    # A deliberate change so we respect it
                    poly_asset.visibility = icosa_asset.visibility

                poly_asset.name = icosa_asset.name or poly_asset.name
                poly_asset.description = icosa_asset.description or poly_asset.description

                # We will keep the poly owner as a backup in case we need to restore
                icosa_asset.owner = poly_owner
                icosa_asset.visibility = "ARCHIVED"  # TODO
                poly_owner.disable_profile = True  # TODO
