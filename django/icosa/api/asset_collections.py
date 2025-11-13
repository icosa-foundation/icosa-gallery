from typing import List

from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    DEFAULT_CACHE_SECONDS,
    NOT_FOUND,
    AssetCollectionPagination,
)
from icosa.models import (
    PRIVATE,
    UNLISTED,
    AssetCollection,
)
from icosa.views.decorators import cache_per_user
from ninja import Router
from ninja.decorators import decorate_view
from ninja.pagination import paginate

from .schema import AssetCollectionSchema

router = Router()


@router.get(
    "",
    response=List[AssetCollectionSchema],
    **COMMON_ROUTER_SETTINGS,
)
@router.get(
    "/",
    include_in_schema=False,
    response=List[AssetCollectionSchema],
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(cache_per_user(DEFAULT_CACHE_SECONDS))
@paginate(AssetCollectionPagination)
def collection_list(request):
    collections = AssetCollection.objects.exclude(visibility__in=[PRIVATE, UNLISTED])
    _ = request
    return collections


@router.get(
    "/{str:asset_collection_url}",
    response=AssetCollectionSchema,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(cache_per_user(DEFAULT_CACHE_SECONDS))
def collection_show(request, asset_collection_url):
    try:
        collection = AssetCollection.objects.exclude(visibility=PRIVATE).get(url=asset_collection_url)
    except AssetCollection.DoesNotExist:
        raise NOT_FOUND
    _ = request
    return collection
