import bcrypt
from django.contrib.auth.models import User as DjangoUser
from django.core.management.base import BaseCommand
from icosa.helpers import YES
from icosa.models import AssetOwner
from icosa.views.auth import save_access_token


class Command(BaseCommand):
    help = """Creates a Django user based on an existing Asset Owner"""

    def add_arguments(self, parser):
        parser.add_argument("--id", action="store", type=str)

    def handle(self, *args, **options):
        id = options["id"]
        if id is None:
            print(
                """
Usage:
--id\tThe primary key of the Asset Owner from which to create a Django User.
                """
            )
            return
        try:
            icosa_user = AssetOwner.objects.get(pk=id)
        except AssetOwner.DoesNotExist:
            print(f"Asset Owner with id `{id}` not found.")
            return

        email = icosa_user.email

        try:
            django_user = DjangoUser.objects.get(username=email)
        except DjangoUser.DoesNotExist:
            django_user = None

        overwriting_django_user = False
        if (
            django_user is not None
            and input(
                f"A Django user with email {email} already exists. Overwrite? "
            ).lower()
            in YES
        ):
            overwriting_django_user = True

        if django_user is not None and not overwriting_django_user:
            print("Quitting. Nothing was changed.")
            return

        new_password = input(
            "Enter a new password for the user (keep blank to use the original password): "
        )
        password = new_password or icosa_user.password
        password = str(password)

        is_staff = (
            input(
                "Allow the user to log in to the Django admin with no permissions by default? "
            )
            in YES
        )
        # Assuming we are overwriting here othewise we would have returned
        # above.
        if django_user is not None:
            django_user = DjangoUser.objects.get(username=email)
            django_user.set_password(password)
            django_user.save()
        else:
            django_user = DjangoUser.objects.create_user(
                username=email,
                email=email,
                password=password,
            )

        django_user.is_staff = is_staff
        django_user.save()

        if new_password:
            salt = bcrypt.gensalt(10)
            hashedpw = bcrypt.hashpw(new_password.encode(), salt)
            icosa_user.password = hashedpw
        icosa_user.migrated = True
        icosa_user.save()
        save_access_token(icosa_user)

        print(f"Finished migrating {email}")
