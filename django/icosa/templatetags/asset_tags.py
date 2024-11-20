from django import template

register = template.Library()


@register.inclusion_tag("main/tags/like_button.html", takes_context=True)
def like_button(context, request, asset):
    is_liked = asset in context.get("user_liked_assets", [])

    return {
        "is_liked": is_liked,
        "asset_url": asset.url,
        "request": request,
    }
