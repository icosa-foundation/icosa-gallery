from django.conf import settings
from icosa.models import AssetOwner


def owner_processor(request):
    return {"owner": AssetOwner.from_django_user(request.user)}


def settings_processor(request):
    can_view_in_maintenance = True

    if settings.MAINTENANCE_MODE:
        can_view_in_maintenance = request.user.is_staff
    return {
        "settings": settings,
        "can_view_in_maintenance": can_view_in_maintenance,
    }


def user_asset_likes_processor(request):
    user = request.user
    liked_assets = []
    if user is not None and not user.is_anonymous:
        liked_assets = user.likes.all()
    return {
        "user_liked_assets": liked_assets,
    }
