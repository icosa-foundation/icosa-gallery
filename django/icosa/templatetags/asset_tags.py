from django import template
from icosa.models import ARCHIVED, PRIVATE, UNLISTED

register = template.Library()


@register.inclusion_tag("main/tags/like_button.html", takes_context=True)
def like_button(context, request, asset):
    is_liked = asset in context.get("user_liked_assets", [])

    return {
        "is_liked": is_liked,
        "asset_url": asset.url,
        "request": request,
    }


@register.inclusion_tag("partials/admin_peek_banner.html", takes_context=True)
def admin_peek_banner(context, request, asset):
    user = request.user
    asset_is_hidden = asset.visibility in [PRIVATE, UNLISTED, ARCHIVED]
    user_is_not_owner = user != asset.owner.django_user
    user_is_privileged = user.is_staff or user.is_superuser
    is_peeking = asset_is_hidden and user_is_not_owner and user_is_privileged

    return {
        "is_peeking_at_asset": is_peeking,
    }
