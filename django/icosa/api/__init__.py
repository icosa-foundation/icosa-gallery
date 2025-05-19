from typing import Any, List, NoReturn, Optional

from django.conf import settings
from django.db.models import Q
from django.http import HttpRequest
from icosa.api.exceptions import FilterException
from icosa.api.schema import FormatFilter
from icosa.models import (
    PRIVATE,
    Asset,
)
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

NOT_FOUND = HttpError(404, "Asset not found.")


def user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    user = request.user
    return user is not None and user == asset.owner.django_user


def check_user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> NoReturn:
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
    asset: str,
) -> Asset:
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(url=asset)
    except Asset.DoesNotExist:
        raise NOT_FOUND
    if not user_can_view_asset(request, asset):
        if settings.DEBUG:
            raise NOT_FOUND
        else:
            raise NOT_FOUND
    return asset


class AssetPagination(PaginationBase):
    class Input(Schema):
        # pageToken and pageSize should really be int, but need to be str so we can accept
        # stuff like ?pageSize=&pageToken=
        # See here: https://github.com/vitalik/django-ninja/issues/807
        pageToken: str = None
        page_token: SkipJsonSchema[str] = None
        pageSize: str = None
        page_size: SkipJsonSchema[str] = None

    class Output(Schema):
        assets: List[Any]
        totalSize: int
        nextPageToken: Optional[str] = None

    items_attribute: str = "assets"

    def paginate_queryset(
        self,
        queryset,
        pagination: Input,
        request,
        **params,
    ):
        try:
            page_size = (
                int(pagination.pageSize)
                or int(pagination.page_size)
                or DEFAULT_PAGE_SIZE
            )
        except (ValueError, TypeError):
            # pageSize could still be defined, but empty: `?pageSize=`).
            page_size = DEFAULT_PAGE_SIZE
        page_size = min(page_size, MAX_PAGE_SIZE)

        try:
            page_token = (
                int(pagination.pageToken)
                or int(pagination.page_token)
                or DEFAULT_PAGE_TOKEN
            )
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
            "assets": queryset[offset : offset + page_size],
            "totalSize": queryset_count,
        }
        if offset + page_size < count:
            pagination_data.update(
                {
                    "nextPageToken": str(page_token + 1),
                }
            )
        return pagination_data


def build_format_q(formats: List) -> Q:
    q = Q()
    valid_q = False
    for format in formats:
        # Reliant on the fact that each of FILTERABLE_FORMATS has an
        # associated has_<format> field in the db.
        format_value = format.value
        if format == FormatFilter.GLTF:
            format_value = "GLTF_ANY"
        if format == FormatFilter.NO_GLTF:
            format_value = "-GLTF_ANY"
        if format_value.startswith("-"):
            q &= Q(**{f"has_{format_value.lower()[1:]}": False})
        else:
            q &= Q(**{f"has_{format_value.lower()}": True})
        valid_q = True

    if valid_q:
        return q
    else:
        choices = ", ".join([x.value for x in FormatFilter])
        raise FilterException(f"Format filter not one of {choices}")

