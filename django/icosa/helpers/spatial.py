from django.db.models import OuterRef, Subquery
from django.db.models.functions import JSONObject

from icosa.models import Format, Resource


def annotate_spatial_resources(queryset, asset_id_field="pk"):
    # Match preferred_viewer_format's first-by-PK selection without a reverse
    # join, which could duplicate listing rows if multiple formats are preferred.
    preferred_resource = (
        Format.objects.filter(asset_id=OuterRef(asset_id_field), is_preferred_for_gallery_viewer=True)
        .order_by("pk")
        .annotate(
            spatial_resource=JSONObject(
                id="root_resource__id",
                file="root_resource__file",
                external_url="root_resource__external_url",
            )
        )
        .values("spatial_resource")[:1]
    )
    return queryset.annotate(spatial_resource=Subquery(preferred_resource))


def get_spatial_portal_urls(items):
    urls = []
    for item in items:
        if item.spatial_resource and item.spatial_resource["id"] is not None:
            # Use the existing storage and CORS rules with data already fetched
            # by the listing query; constructing a Resource does not query it.
            resource = Resource(**item.spatial_resource)
            if portal_url := resource.internal_or_cors_url:
                urls.append(portal_url)
    return urls
