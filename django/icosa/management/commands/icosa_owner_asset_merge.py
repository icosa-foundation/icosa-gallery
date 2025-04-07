from django.core.management import BaseCommand
from icosa.helpers import YES
from icosa.models import PRIVATE, Asset


def printlog(dry_run, message):
    if dry_run:
        prefix = "-- dry run -- "
    else:
        prefix = ""
    print(f"{prefix}{message}")


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--dryrun",
            action="store_true",
        )

    def handle(self, *args, **options):
        dry_run = options["dryrun"]

        if not dry_run:
            if input("`--dryrun` is not set. Will really modify assets. Continue? ").lower() not in YES:
                print("Quitting")
                return

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

            # Merge poly_owner assets into icosa_owner
            for poly_asset in poly_owner.assets.all():
                printlog(
                    dry_run,
                    f"Change ower for poly_asset `{poly_asset.name} - {poly_asset.id}` from `{poly_asset.owner.displayname} - {poly_asset.owner.id}` to `{icosa_owner.displayname} - {icosa_owner.id}`",
                )
                poly_asset.owner = icosa_owner

                if not dry_run:
                    poly_asset.save()

            for asset in asset_matches[icosa_owner]:
                icosa_asset, poly_asset = asset
                if not dry_run:
                    icosa_owner.refresh_from_db()
                    poly_owner.refresh_from_db()

                if icosa_asset.visibility == PRIVATE:
                    # Most likely the user never changed the default visibility
                    pass
                else:
                    printlog(
                        dry_run,
                        f"Change visibility for poly_asset `{poly_asset.name} - {poly_asset.id}` from `{poly_asset.visibility}` to `{icosa_asset.visibility}`",
                    )
                    # A deliberate change so we respect it
                    poly_asset.visibility = icosa_asset.visibility

                if icosa_asset.name:
                    printlog(
                        dry_run,
                        f"Change name for poly_asset `{poly_asset.name} - {poly_asset.id}` from `{poly_asset.name}` to `{icosa_asset.name}`",
                    )
                    poly_asset.name = icosa_asset.name

                if icosa_asset.description:
                    printlog(
                        dry_run,
                        f"Change description for poly_asset `{poly_asset.description} - {poly_asset.id}` from `{poly_asset.description}` to `{icosa_asset.description}`",
                    )
                    poly_asset.description = icosa_asset.description

                # We will keep the poly owner as a backup in case we need to restore
                printlog(
                    dry_run,
                    f"Change owner for icosa_asset `{poly_asset.description} - {poly_asset.id}` from `{icosa_owner.displayname}- {icosa_owner.id}` to `{poly_owner.displayname}- {poly_owner.id}`",
                )
                icosa_asset.owner = poly_owner

                icosa_asset.visibility = "ARCHIVED"  # TODO
                poly_owner.disable_profile = True  # TODO
                if not dry_run:
                    icosa_asset.save()
                    poly_asset.save()
                    poly_owner.save()
