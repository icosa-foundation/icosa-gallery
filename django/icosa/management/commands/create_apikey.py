from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "Create an api key for a user"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username of the user")

    def handle(self, *args, **kwargs):
        username = kwargs["username"]
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError('User "%s" does not exist' % username)

        token = user.generate_access_token()

        self.stdout.write(self.style.SUCCESS("%s" % token))
