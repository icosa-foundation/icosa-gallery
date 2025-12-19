import re
from typing import List

from constance import config
from django.db.models import Q
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    DEFAULT_CACHE_SECONDS,
    NOT_FOUND,
    AssetPagination,
    get_asset_by_url,
)
from icosa.models import (
    ALL_RIGHTS_RESERVED,
    ARCHIVED,
    PRIVATE,
    PUBLIC,
    UNLISTED,
    Asset,
)
from icosa.views.decorators import cache_per_user
from ninja import Query, Router
from ninja.decorators import decorate_view
from ninja.pagination import paginate

from .filters import (
    FiltersAsset,
    FiltersOrder,
    filter_and_sort_assets,
)
from .schema import (
    AssetSchema,
    AssetStateSchema,
)

router = Router()


IMAGE_REGEX = re.compile("(jpe?g|tiff?|png|webp|bmp)")


@router.get(
    "/{str:asset_url}",
    response=AssetSchema,
    **COMMON_ROUTER_SETTINGS,
)
def get_asset(
    request,
    asset_url: str,
):
    try:
        asset = Asset.objects.exclude(visibility=ARCHIVED).get(url=asset_url)
    except Asset.DoesNotExist:
        raise NOT_FOUND
    if asset.visibility == PRIVATE:
        # TODO `check_user_owns_asset` is not appropriate here. Perhaps
        # refactor it to be more useful.
        if asset.owner.django_user != request.user:
            raise NOT_FOUND
    return asset


@router.get(
    "/{str:asset_url}/upload_state",
    response={200: AssetStateSchema},
    **COMMON_ROUTER_SETTINGS,
    include_in_schema=False,  # TODO, should this be advertised?
)
@decorate_view(cache_per_user(DEFAULT_CACHE_SECONDS))
def asset_upload_state(
    request,
    asset_url: str,
):
    asset = get_asset_by_url(request, asset_url)
    return asset


@router.get(
    "",
    response=List[AssetSchema],
    **COMMON_ROUTER_SETTINGS,
    url_name="asset_list",
)
@router.get(
    "/",
    response=List[AssetSchema],
    include_in_schema=False,
    **COMMON_ROUTER_SETTINGS,
    url_name="asset_list",
)
@paginate(AssetPagination)
@decorate_view(cache_per_user(DEFAULT_CACHE_SECONDS))
def get_assets(
    request,
    order: FiltersOrder = Query(...),
    filters: FiltersAsset = Query(...),
):
    exc_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED)
    if config.HIDE_REPORTED_ASSETS:
        exc_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED) | Q(last_reported_time__isnull=False)

    assets = filter_and_sort_assets(
        filters,
        order,
        assets=Asset.objects.filter(visibility=PUBLIC),
        exc_q=exc_q,
    )

    return assets
