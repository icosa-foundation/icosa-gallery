from typing import Optional

from icosa.api.schema import OembedOut
from icosa.models import Asset
from ninja import Router

from django.http import HttpResponse, HttpResponseNotFound
from django.urls import resolve

router = Router()

# TODO add rel tags to asset pages
# examples
# <link rel="alternate" type="application/json+oembed" href="https://timnash.co.uk//wp-json/oembed/?url=https://timnash.co.uk//structuring-next-wordpress-project/"
#   title="Structuring your next WordPress project" />
# <link rel="alternate" type="application/json+oembed" href="https://sketchfab.com/oembed?url=https%3A%2F%2Fsketchfab.com%2F3d-models%2Fpostbirb-diorama-4e44267561304408852799942a1f9a9a"
#   title="PostBirb Diorama - 3D model by JuanchoAbad (@juanchodeth)">


@router.get("", response=OembedOut)
def oembed(
    request,
    url: str = None,
    format: Optional[str] = None,
    maxwidth: Optional[int] = None,
    maxheight: Optional[int] = None,
):
    if format != "json" and format is not None:
        return HttpResponse("Not implemented", status_code=501)
    url = url.replace(f"{request.scheme}://{request.get_host()}", "")
    match = resolve(url)
    if match.url_name != "view_asset":
        return HttpResponseNotFound("Not found")
    asset = asset = Asset.objects.get(url=match.kwargs["asset_url"])
    # TODO Implement a view for "asset.get_absolute_url()}/embed/" - minimal viewer markup suitable for embedding
    return {
        "type": "rich",
        "version": "1.0",
        "title": asset.name,
        "author_name": asset.owner.displayname,
        "author_url": asset.owner.get_absolute_url(),
        "provider_name": "Icosa",  # TODO make configurable
        "provider_url": request.get_host(),  # TODO is this always correct?
        "thumbnail_url": asset.thumbnail,  # TODO resize to maxwidth / maxheight
        "thumbnail_width": "256",  # TODO Must obey maxwidth (?)
        "thumbnail_height": "256",  # TODO Must obey maxheight (?)
        "html": f"""<div class="icosa-embed-wrapper">
<iframe id="" title="" class="" width="800" height="600" src="{asset.get_absolute_url()}/embed/" frameborder="0" allow="autoplay; fullscreen; xr-spatial-tracking" allowfullscreen="" mozallowfullscreen="true" webkitallowfullscreen="true" xr-spatial-tracking="true" execution-while-out-of-viewport="true" execution-while-not-rendered="true" web-share="true">
</iframe></div>""",  # TODO The HTML required to embed a video player. The HTML should have no padding or margins.
        "width": "800",  # TODO The width in pixels of the resource. Must obey maxwidth
        "height": "600",  # TODO The height in pixels of the resource. Must obey maxheight
    }
