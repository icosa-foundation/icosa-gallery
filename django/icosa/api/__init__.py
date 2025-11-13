from typing import Any, List, Optional

from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from icosa.models import PRIVATE, Asset, AssetCollection
from ninja import Schema
from ninja.errors import HttpError
from ninja.pagination import PaginationBase
from pydantic.json_schema import SkipJsonSchema

COMMON_ROUTER_SETTINGS = {
    "exclude_none": True,
    "exclude_defaults": True,
}

POLY_CATEGORY_MAP = {
    "TECHNOLOGY": "TECH",
}

DEFAULT_PAGE_SIZE = 20
DEFAULT_PAGE_TOKEN = 1
MAX_PAGE_SIZE = 100

DEFAULT_CACHE_SECONDS = 10

NOT_FOUND = HttpError(404, "Asset not found.")


def get_publish_url(request, asset: Asset, response_code=200) -> tuple[int, dict[str, Any]]:
    url = request.build_absolute_uri(
        reverse(
            "icosa:asset_publish",
            kwargs={
                "asset_url": asset.url,
            },
        )
    )
    if settings.DEPLOYMENT_HOST_API is not None:
        url = url.replace(settings.DEPLOYMENT_HOST_API, settings.DEPLOYMENT_HOST_WEB)
    return response_code, {
        "publishUrl": url,
        "assetId": asset.url,
    }


def user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    user = request.user
    return user is not None and user == asset.owner.django_user


def check_user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> None:
    if not user_owns_asset(request, asset):
        raise


def user_can_view_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    if asset.visibility == PRIVATE:
        return user_owns_asset(request, asset)
    return True


def get_asset_by_url(
    request: HttpRequest,
    asset_url: str,
) -> Asset:
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(url=asset_url)
    except Asset.DoesNotExist:
        raise NOT_FOUND
    if not user_can_view_asset(request, asset):
        if settings.DEBUG:
            raise NOT_FOUND
        else:
            raise NOT_FOUND
    return asset


class IcosaPagination(PaginationBase):
    class Input(Schema):
        # pageToken and pageSize should really be int, but need to be str so we can accept
        # stuff like ?pageSize=&pageToken=
        # See here: https://github.com/vitalik/django-ninja/issues/807
        pageToken: Optional[str] = None
        page_token: SkipJsonSchema[Optional[str]] = None
        pageSize: Optional[str] = None
        page_size: SkipJsonSchema[Optional[str]] = None

    class Output(Schema):
        items: List[Any]
        totalSize: int
        nextPageToken: Optional[str] = None

    items_attribute: str = "items"

    def paginate_queryset(
        self,
        queryset,
        pagination: Input,
        **params,
    ):
        try:
            page_size = int(pagination.pageSize) or int(pagination.page_size) or DEFAULT_PAGE_SIZE
        except (ValueError, TypeError):
            # pageSize could still be defined, but empty: `?pageSize=`).
            page_size = DEFAULT_PAGE_SIZE
        page_size = min(page_size, MAX_PAGE_SIZE)

        try:
            page_token = int(pagination.pageToken) or int(pagination.page_token) or DEFAULT_PAGE_TOKEN
        except (ValueError, TypeError):
            # pageToken could still be defined, but empty: `?pageToken=`).
            page_token = DEFAULT_PAGE_TOKEN

        offset = (page_token - 1) * page_size
        count = self._items_count(queryset)
        if type(queryset) is list:
            queryset_count = len(queryset)
        else:
            queryset_count = queryset.count()
        pagination_data = {
            self.items_attribute: queryset[offset : offset + page_size],
            "totalSize": queryset_count,
        }
        if offset + page_size < count:
            pagination_data.update(
                {
                    "nextPageToken": str(page_token + 1),
                }
            )
        return pagination_data


class AssetPagination(IcosaPagination):
    class Output(Schema):
        assets: List[Any]
        totalSize: int
        nextPageToken: Optional[str] = None

    items_attribute: str = "assets"


class AssetCollectionPagination(IcosaPagination):
    class Output(Schema):
        collections: List[Any]
        totalSize: int
        nextPageToken: Optional[str] = None

    items_attribute: str = "collections"
