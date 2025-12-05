from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from icosa.helpers import YES
from icosa.models import Asset, AssetOwner, DeviceCode, UserLike


def print_actions(
    source_repr,
    source_owner,
    destination_repr,
    destination_owner,
    assets,
    likes,
    reports,
    overwrite_email,
    overwrite_description,
    overwrite_displayname,
):
    print(f"\nMove the following from {source_repr} to {destination_repr}:")
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

    if overwrite_email:
        print(f"\nChange email from {destination_owner.email} to {source_owner.email}")
    if overwrite_description:
        print(f"\nChange description from {destination_owner.description} to {source_owner.description}")
    if overwrite_displayname:
        print(f"\nChange displayname from {destination_owner.displayname} to {source_owner.displayname}")


class Command(BaseCommand):
    help = """Extracts format json into concrete models and converts to poly
    format."""

    def add_arguments(self, parser):
        parser.add_argument("--sourceid", action="store", type=str)
        parser.add_argument("--destinationid", action="store", type=str)
        parser.add_argument(
            "--overwrite-email",
            action="store_true",
        )
        parser.add_argument(
            "--overwrite-displayname",
            action="store_true",
        )
        parser.add_argument(
            "--overwrite-description",
            action="store_true",
        )

    def handle(self, *args, **options):
        source_id = options["sourceid"]
        destination_id = options["destinationid"]
        overwrite_email = options["overwrite_email"]
        overwrite_displayname = options["overwrite_displayname"]
        overwrite_description = options["overwrite_description"]

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
            print(f"Source Asset Owner with id `{source_id}` not found.")
            return
        try:
            destination_owner = AssetOwner.objects.get(pk=destination_id)
        except AssetOwner.DoesNotExist:
            print(f"Destination Asset Owner with id `{destination_id}` not found.")
            return

        source_repr = f"`{source_owner.displayname}` (id: {source_owner.id})"
        destination_repr = f"`{destination_owner.displayname}` (id: {destination_owner.id})"

        # Hard fail if we are overwriting with blank values
        if any([overwrite_email, overwrite_displayname, overwrite_description]):
            if overwrite_email and not source_owner.email:
                print(f"Error: --overwrite_email was set, but {source_owner} email is blank. Unset this to continue.")
                return
            if overwrite_description and not source_owner.description:
                print(
                    f"Error: --overwrite_description was set, but {source_owner} description is blank. Unset this to continue."
                )
                return
            if overwrite_displayname and not source_owner.displayname:
                print(
                    f"Error: --overwrite_displayname was set, but {source_owner} displayname is blank. Unset this to continue."
                )
                return

        assets = Asset.objects.filter(owner=source_owner)
        if source_owner.django_user:
            likes = UserLike.objects.filter(user=source_owner.django_user)
            reports = Asset.objects.filter(last_reported_by=source_owner.django_user)
            device_codes = DeviceCode.objects.filter(user=source_owner.django_user)
        else:
            likes = UserLike.objects.none()
            reports = Asset.objects.none()
            device_codes = DeviceCode.objects.none()
            print(
                f"{source_repr} does not have an associated django user, so will not move any likes, reports or device codes."
            )

        action = None

        overwrite_prompt = ""
        if any([overwrite_email, overwrite_displayname, overwrite_description]):
            overwrite_prompt += "Will also:"
            if overwrite_email:
                overwrite_prompt += f"\nChange email from {destination_owner.email} to {source_owner.email}"
            if overwrite_description:
                overwrite_prompt += (
                    f"\nChange description from {destination_owner.description} to {source_owner.description}"
                )
            if overwrite_displayname:
                overwrite_prompt += (
                    f"\nChange displayname from {destination_owner.displayname} to {source_owner.displayname}"
                )
        action = input(
            f"""Will move:
\n{assets.count()} Assets
{reports.count()} "Last reported" attributions on Assets
from {source_repr} to {destination_repr}
{overwrite_prompt}
\nand will expire any active device codes.
\nDo you want to continue? [(y)es,(n)o,(l)ist objects] [n] """
        ).lower()

        do_work = False
        if action in YES:
            do_work = True
        if action == "l":
            print("The following objects would be done:")
            print_actions(
                source_repr,
                source_owner,
                destination_repr,
                destination_owner,
                assets,
                likes,
                reports,
                overwrite_email,
                overwrite_description,
                overwrite_displayname,
            )

        if not do_work:
            print("\nQuitting without doing anything.")
            return

        print("\nDoing the following:")
        print_actions(
            source_repr,
            source_owner,
            destination_repr,
            destination_owner,
            assets,
            likes,
            reports,
            overwrite_email,
            overwrite_description,
            overwrite_displayname,
        )

        assets.update(owner=destination_owner)
        reports.update(last_reported_by=destination_owner)
        device_codes.delete()

        if overwrite_email and source_owner.email:
            destination_owner.email = source_owner.email
        if overwrite_description and source_owner.description:
            destination_owner.description = source_owner.description
        if overwrite_displayname and source_owner.displayname:
            destination_owner.displayname = source_owner.displayname
        destination_owner.save()

        if source_owner.django_user:
            source_owner.django_user.active = False
            source_owner.django_user.save()
        source_owner.merged_with = destination_owner
        source_owner.save()

        change_url_source = reverse(
            "admin:icosa_assetowner_change",
            args=(source_owner.id,),
        )
        change_url_destination = reverse(
            "admin:icosa_assetowner_change",
            args=(destination_owner.id,),
        )
        print(
            f"\nVisit the admin for the source owner at {settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{change_url_source}"
        )
        print(
            f"Visit the admin for the destination owner at {settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}{change_url_destination}"
        )
        print("\nDone")
