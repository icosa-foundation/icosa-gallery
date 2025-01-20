from django.conf import settings
from icosa.helpers.user import get_owner
from icosa.models import AssetOwner


def owner_processor(request):
    return {"owner": get_owner(request.user)}


def settings_processor(request):
    can_view_in_maintenance = True

    if settings.MAINTENANCE_MODE:
        can_view_in_maintenance = request.user.is_staff
    return {
        "settings": settings,
        "can_view_in_maintenance": can_view_in_maintenance,
    }


def user_asset_likes_processor(request):
    owner = AssetOwner.from_django_request(request)
    liked_assets = []
    if owner is not None:
        liked_assets = owner.likes.all()
    return {
        "user_liked_assets": liked_assets,
    }
