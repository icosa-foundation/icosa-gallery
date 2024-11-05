from icosa.helpers.user import get_owner

from django.conf import settings


def owner_processor(request):
    return {"owner": get_owner(request.user)}


def settings_processor(request):
    return {"settings": settings}
