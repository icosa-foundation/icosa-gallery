import constance
from asgiref.sync import sync_to_async
from django.conf import settings


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


@sync_to_async
def async_constance_config(request):
    """
    Simple context processor that puts the config into every
    RequestContext. Just make sure you have a setting like this:

        TEMPLATE_CONTEXT_PROCESSORS = (
            # ...
            'constance.context_processors.config',
        )

    """
    return {"config": constance.config}
