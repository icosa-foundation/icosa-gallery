from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
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
        print("Reports:")
        for report in reports:
            print(f"\t{report} asset id: {report.id}")


def finish_merge(source_owner, destination_owner):
    source_owner.django_user.active = False
    source_owner.django_user.save()
    source_owner.merged_with = destination_owner
    source_owner.save()


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
            finish_merge(source_owner, destination_owner)
            print("\nDone")
            return

        elif is_interactive:
            action = input(
                f"""Will move:
\n{assets.count()} Assets
{likes.count()} Likes
{reports.count()} "Last reported" attributions on Assets
from {source_owner} to {destination_owner}
\nand will expire any active device codes.
Do you want to continue? [(y)es,(n)o,(l)ist objects] [n] """
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

        source_repr = f"{source_owner.displayname} (id: {source_owner.id})"
        destination_repr = f"{destination_owner.displayname} (id: {destination_owner.id})"
        print(f"Moving the following from {source_repr} to {destination_repr}:")
        print_actions(assets, likes, reports)

        assets.update(owner=destination_owner)
        likes.update(user=destination_owner)
        reports.update(last_reported_by=destination_owner)
        device_codes.delete()

        finish_merge(source_owner, destination_owner)
        change_url = reverse(
            "admin:icosa_assetowner_change",
            args=(source_owner.id,),
        )
        print(
            f"Visit the admin for the old source owner at {settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{change_url}"
        )
        print("\nDone")
