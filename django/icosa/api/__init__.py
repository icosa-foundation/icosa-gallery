from typing import Any, List, Optional

from ninja import Field, Schema
from ninja.pagination import PaginationBase

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
    # only `skip` param, defaults to 5 per page
    class Input(Schema):
        pageToken: int = Field(1, ge=1)
        pageSize: int = None

    class Output(Schema):
        assets: List[Any]  # `items` is a default attribute
        totalSize: int
        nextPageToken: Optional[str] = None

    items_attribute: str = "assets"

    def paginate_queryset(
        self, queryset, pagination: Input, request, **params
    ):
        pageSize = pagination.pageSize or 20
        if pageSize > 100:
            pageSize = 100
        offset = (pagination.pageToken - 1) * pageSize
        count = self._items_count(queryset)
        if type(queryset) == list:
            queryset_count = len(queryset)
        else:
            queryset_count = queryset.count()
        pagination_data = {
            "assets": queryset[offset : offset + pageSize],
            "totalSize": queryset_count,
        }
        if offset + pageSize < count:
            pagination_data.update(
                {
                    "nextPageToken": str(pagination.pageToken + 1),
                }
            )
        return pagination_data
