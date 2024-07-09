from typing import Any, List, Optional

from ninja import Field, Schema
from ninja.pagination import PaginationBase

COMMON_ROUTER_SETTINGS = {
    "exclude_none": True,
    "exclude_defaults": True,
}


class AssetPagination(PaginationBase):
    # only `skip` param, defaults to 5 per page
    class Input(Schema):
        page: int = Field(1, ge=1)
        pageSize: int = None

    class Output(Schema):
        assets: List[Any]  # `items` is a default attribute
        totalSize: int
        pageToken: Optional[str] = None

    items_attribute: str = "assets"

    def paginate_queryset(
        self, queryset, pagination: Input, request, **params
    ):
        pageSize = pagination.pageSize or 20
        offset = (pagination.page - 1) * pageSize
        count = self._items_count(queryset)
        pagination_data = {
            "assets": queryset[offset : offset + pageSize],
            "totalSize": queryset.count(),
        }
        if offset + pageSize < count:
            ps_query = ""
            if pagination.pageSize is not None:
                ps_query = f"&pageSize={pageSize}"

            next = request.build_absolute_uri(
                f"{request.path}?page={str(pagination.page + 1)}{ps_query}"
            )
            pagination_data.update(
                {
                    "pageToken": next,
                }
            )
        return pagination_data
