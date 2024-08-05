from typing import Any, List, Optional

from ninja import NinjaAPI, Schema, Swagger
from ninja.pagination import PaginationBase
from ninja.types import DictStrAny

from django.conf import settings

COMMON_ROUTER_SETTINGS = {
    "exclude_none": True,
    "exclude_defaults": True,
}

POLY_CATEGORY_MAP = {
    "ANIMALS": "animals",
    "ARCHITECTURE": "architecture",
    "ART": "art",
    "FOOD": "food",
    "NATURE": "nature",
    "OBJECTS": "objects",
    "PEOPLE": "people",
    "PLACES": "scenes",
    "TECH": "tech",
    "TECHNOLOGY": "tech",
    "TRANSPORT": "transport",
}


class AssetPagination(PaginationBase):
    class Input(Schema):
        pageToken: int = None
        page_token: int = None
        pageSize: int = None
        page_size: int = None

    class Output(Schema):
        assets: List[Any]
        totalSize: int
        nextPageToken: Optional[str] = None

    items_attribute: str = "assets"

    def paginate_queryset(
        self, queryset, pagination: Input, request, **params
    ):
        page_size = pagination.pageSize or pagination.page_size or 20
        if page_size > 100:
            page_size = 100
        page_token = pagination.pageToken or pagination.page_token or 1
        offset = (page_token - 1) * page_size
        count = self._items_count(queryset)
        if type(queryset) == list:
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
