from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import resolve
from icosa.api.schema import OembedOut
from icosa.models import Asset
from ninja import Router
from ninja.errors import HttpError

router = Router()

# TODO add rel tags to asset pages
# examples
# <link rel="alternate" type="application/json+oembed" href="https://timnash.co.uk//wp-json/oembed/?url=https://timnash.co.uk//structuring-next-wordpress-project/"
#   title="Structuring your next WordPress project" />
# <link rel="alternate" type="application/json+oembed" href="https://sketchfab.com/oembed?url=https%3A%2F%2Fsketchfab.com%2F3d-models%2Fpostbirb-diorama-4e44267561304408852799942a1f9a9a"
#   title="PostBirb Diorama - 3D model by JuanchoAbad (@juanchodeth)">


def calc_width(height):
    return round(height * (8 / 6))


def calc_height(width):
    return round(width * (6 / 8))


def calc_dimensions(maxwidth, maxheight):
    if maxwidth and maxheight:
        if maxwidth < maxheight:
            frame_width = maxwidth
            frame_height = calc_height(maxwidth)
        else:
            frame_height = maxheight
            frame_width = calc_width(maxheight)
    elif maxwidth:
        frame_width = maxwidth
        frame_height = calc_height(maxwidth)
    elif maxheight:
        frame_height = maxheight
        frame_width = calc_width(maxheight)
    else:
        frame_width = 1920
        frame_height = 1440

    return (frame_width, frame_height)


@router.get("", response=OembedOut)
def oembed(
    request,
    url: str = None,
    format: Optional[str] = None,
    maxwidth: Optional[int] = None,
    maxheight: Optional[int] = None,
):
    if not url:
        raise HttpError(404, "Not found.")

    if format != "json" and format is not None:
        raise HttpError(501, "Not implemented.")
    url = url.replace(f"{request.scheme}://{request.get_host()}", "")
    match = resolve(url)
    if match.url_name != "asset_oembed":
        raise HttpError(404, "Not found.")
    asset = asset = Asset.objects.get(url=match.kwargs["asset_url"])

    frame_width, frame_height = calc_dimensions(maxwidth, maxheight)

    host = f"{settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}"

    embed_code = render_to_string(
        "partials/oembed_code.html",
        {
            "host": host,
            "asset": asset,
            "frame_width": frame_width,
            "frame_height": frame_height,
        },
    )
    return {
        "type": "rich",
        "version": "1.0",
        "title": asset.name,
        "author_name": asset.owner.displayname,
        "author_url": f"{host}{asset.owner.django_user.get_absolute_url()}" if asset.owner.django_user else "",
        "provider_name": "Icosa",  # TODO make configurable
        "provider_url": host,
        "thumbnail_url": asset.thumbnail,  # TODO resize to maxwidth / maxheight
        "thumbnail_width": "256",  # TODO Must obey maxwidth (?)
        "thumbnail_height": "256",  # TODO Must obey maxheight (?)
        "html": embed_code.strip(),
        "width": f"{frame_width}",
        "height": f"{frame_height}",
    }
