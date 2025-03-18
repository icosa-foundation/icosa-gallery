from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string

from ...models import UserAPIKey

User = get_user_model()

class Command(BaseCommand):
    help = 'Create an api key for a user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username of the user')
        parser.add_argument('name', type=str, help='name of the key')

    def handle(self, *args, **kwargs):
        username = kwargs['username']
        name = kwargs['name']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError('User "%s" does not exist' % username)

        _,key = UserAPIKey.objects.create_key(user=user, name=name)

        self.stdout.write(self.style.SUCCESS("%s" % key))