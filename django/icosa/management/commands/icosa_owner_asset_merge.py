from django.core.management import BaseCommand
from icosa.helpers import YES
from icosa.models import ARCHIVED, PRIVATE, Asset

SKIP_ASSET_OWNER_IDS = [
    63664420588408665,
    62557179709778192,
    804,
    18169,
]


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

            if icosa_asset.owner.id in SKIP_ASSET_OWNER_IDS or poly_asset.owner.id in SKIP_ASSET_OWNER_IDS:
                continue

            owner_match = (icosa_asset.owner, poly_asset.owner)
            owner_matches.add(owner_match)
            key = icosa_asset.owner.id
            if key not in asset_matches:
                asset_matches[key] = []
            asset_matches[key].append((icosa_asset, poly_asset))

        # 1308 have become PRIVATE from PUBLIC
        # private was the default so the 1308 were people doing nothing except importing.
        # I propose we respect deliberate changes. i.e. we ignore the 1308
        # Copy over name and description changes from the icosa version and then delete the icosa version to remove duplicates

        for owners in owner_matches:
            icosa_owner, poly_owner = owners

            # Merge poly_owner assets into icosa_owner
            for poly_asset in poly_owner.asset_set.all():
                msg = f"Change owner for poly_asset `{poly_asset.name}::{poly_asset.id}` FROM `{poly_asset.owner.displayname}::{poly_asset.owner.id}` TO `{icosa_owner.displayname}::{icosa_owner.id}`"
                printlog(dry_run, msg)
                poly_asset.owner = icosa_owner

                if not dry_run:
                    poly_asset.save()

            for item in asset_matches[icosa_owner.id]:
                icosa_asset, poly_asset = item
                if not dry_run:
                    icosa_owner.refresh_from_db()
                    poly_owner.refresh_from_db()

                if icosa_asset.visibility == PRIVATE:
                    # Most likely the user never changed the default visibility
                    pass
                elif icosa_asset.visibility != poly_asset.visibility:
                    msg = f"Change visibility for poly_asset `{poly_asset.name}::{poly_asset.id}` FROM `{poly_asset.visibility}` TO `{icosa_asset.visibility}`"
                    printlog(dry_run, msg)
                    # A deliberate change so we respect it
                    poly_asset.visibility = icosa_asset.visibility

                if icosa_asset.name and icosa_asset.name != poly_asset.name:
                    msg = f"Change name for poly_asset `{poly_asset.name}::{poly_asset.id}` FROM `{poly_asset.name}` TO `{icosa_asset.name}`"
                    printlog(dry_run, msg)
                    poly_asset.name = icosa_asset.name

                if icosa_asset.description and icosa_asset.description != poly_asset.description:
                    msg = f"Change description for poly_asset `{poly_asset.name}::{poly_asset.id}` FROM `{len(poly_asset.description)}` TO `{len(icosa_asset.description)}`"
                    printlog(dry_run, msg)
                    poly_asset.description = icosa_asset.description

                # We will keep the poly owner as a backup in case we need to restore
                msg = f"Change owner for icosa_asset `{icosa_asset.name}::{icosa_asset.id}` FROM `{icosa_owner.displayname}::{icosa_owner.id}` TO `{poly_owner.displayname}::{poly_owner.id}`"
                printlog(dry_run, msg)
                icosa_asset.owner = poly_owner

                polydata = icosa_asset.polydata
                polydata.update({"previous_visibility": icosa_asset.visibility})
                icosa_asset.visibility = ARCHIVED  # TODO
                icosa_asset.polydata = polydata
                poly_owner.disable_profile = True  # TODO
                if not dry_run:
                    icosa_asset.save()
                    poly_asset.save()
                    poly_owner.save()
