from icosa.models import User as IcosaUser

from django import template

register = template.Library()


@register.inclusion_tag("main/tags/like_button.html")
def like_button(request, asset):
    owner = IcosaUser.from_request(request)
    if owner is not None:
        is_liked = asset.id in owner.likes.values_list("id", flat=True)
    else:
        is_liked = False

    return {"is_liked": is_liked, "request": request}
