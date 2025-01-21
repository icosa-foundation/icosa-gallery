from django.core.management.base import BaseCommand
from icosa.helpers import YES
from icosa.models import Asset, AssetOwner, DeviceCode, OwnerAssetLike


def print_actions(assets, likes, reports):
    if len(assets):
        print("Assets:")
        for asset in assets:
            print(f"\t`{asset}` - asset id: {asset.id}")
    if len(likes):
        print("Likes:")
        for like in likes:
            print(f"\t{like} - like id: {like.id}")
    if len(reports):
        print("Likes:")
        for report in reports:
            print(f"\t{report} asset id: {report.id}")


def merge(source_owner, destination_owner):
    # TODO(james): We will want to handle associated Django users here. What to
    # do: delete, mark as inactive, something else?
    source_owner.merged_with = destination_owner
    source_owner.save()


def ask_to_merge(source_owner, destination_owner):
    if (
        input(
            f"Mark {source_owner} as merged with {destination_owner}? Default is yes. "
        ).strip()
        or "y" in YES
    ):
        merge(source_owner, destination_owner)


class Command(BaseCommand):
    help = """Extracts format json into concrete models and converts to poly
    format."""

    def add_arguments(self, parser):
        parser.add_argument("--sourceid", action="store", type=str)
        parser.add_argument("--destinationid", action="store", type=str)
        parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="""
Don't prompt. Assume `yes` to moving assets and marking as merged. Useful when
running as a script or as a result of user confirmation elsewhere.
            """,
        )

    def handle(self, *args, **options):
        source_id = options["sourceid"]
        destination_id = options["destinationid"]
        is_interactive = not options["non_interactive"]

        if source_id is None or destination_id is None:
            print(
                """
Usage:
--sourceid\tThe primary key of the Asset Owner to move assets and likes from
--destinationid\tThe primary key of the Asset Owner to move assets and likes to
                """
            )
            return
        try:
            source_owner = AssetOwner.objects.get(pk=source_id)
        except AssetOwner.DoesNotExist:
            print(f"Asset Owner with id `{source_id}` not found.")
            return
        try:
            destination_owner = AssetOwner.objects.get(pk=destination_id)
        except AssetOwner.DoesNotExist:
            print(f"Asset Owner with id `{destination_id}` not found.")
            return
        assets = Asset.objects.filter(owner=source_owner)
        likes = OwnerAssetLike.objects.filter(user=source_owner)
        reports = Asset.objects.filter(last_reported_by=source_owner)
        device_codes = DeviceCode.objects.filter(user=source_owner)

        action = None
        if not assets and not likes and not reports:
            print(f"{source_owner} doesn't own any Assets, Likes or Reports.")
            if is_interactive:
                ask_to_merge(source_owner, destination_owner)
            else:
                merge(source_owner, destination_owner)

            print("\nDone")
            return
        elif is_interactive:
            action = input(
                f"""Will move:
    \n{assets.count()} Assets
    {likes.count()} Likes
    {reports.count()} Reports of inappropriate Assets
    from {source_owner} to {destination_owner}
    \nand will expire any active device codes.
    Do you want to continue? Default is `no`. [(y)es,(n)o,(l)ist objects] """
            ).lower()

        do_work = False
        if not is_interactive or action in YES:
            do_work = True
        if action == "l":
            print("The following objects would be moved:")
            print_actions(assets, likes, reports)

        if not do_work:
            print("\nQuitting without doing anything.")
            return

        print(
            "Moving the following objects from {source_owner} to {destination_owner}:"
        )
        print_actions(assets, likes, reports)

        assets.update(owner=destination_owner)
        likes.update(user=destination_owner)
        reports.update(last_reported_by=destination_owner)
        device_codes.delete()

        if is_interactive:
            ask_to_merge(source_owner, destination_owner)
        else:
            merge(source_owner, destination_owner)
        print("\nDone")
