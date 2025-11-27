from django.conf import settings
from icosa.models import UserLike


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
    liked_asset_ids = []
    if user is not None and not user.is_anonymous:
        liked_asset_ids = list(user.likedassets.all().values_list("asset", flat=True))
    return {
        "user_liked_asset_ids": liked_asset_ids,
    }
