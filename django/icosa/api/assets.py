import re
import secrets
from typing import List, Optional

from constance import config
from django.db import transaction
from django.db.models import F, Q
from django.db.models.query import QuerySet
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    DEFAULT_CACHE_SECONDS,
    NOT_FOUND,
    POLY_CATEGORY_MAP,
    AssetPagination,
    build_format_q,
    check_user_owns_asset,
    get_asset_by_url,
    get_publish_url,
)
from icosa.api.exceptions import FilterException
from icosa.helpers.snowflake import generate_snowflake
from icosa.jwt.authentication import JWTAuth
from icosa.models import (
    ALL_RIGHTS_RESERVED,
    PUBLIC,
    UNLISTED,
    Asset,
    AssetOwner,
)
from icosa.tasks import queue_blocks_upload_format, queue_finalize_asset
from icosa.views.decorators import cache_per_user
from ninja import File, Query, Router
from ninja.decorators import decorate_view
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate

from .schema import (
    ORDER_FIELD_MAP,
    AssetFilters,
    AssetFinalizeData,
    AssetSchema,
    AssetStateSchema,
    Order,
    SortDirection,
    UploadJobSchemaOut,
    filter_complexity,
    filter_license,
    filter_triangle_count,
    filter_zip_archive_url,
    get_keyword_q,
)

router = Router()


IMAGE_REGEX = re.compile("(jpe?g|tiff?|png|webp|bmp)")


@router.get(
    "/{str:asset}",
    response=AssetSchema,
    **COMMON_ROUTER_SETTINGS,
)
def get_asset(
    request,
    asset: str,
):
    try:
        asset = Asset.objects.get(url=asset)
    except Asset.DoesNotExist:
        raise NOT_FOUND
    if asset.visibility not in [PUBLIC, UNLISTED]:
        raise NOT_FOUND
    return asset


@router.get(
    "/{str:asset}/upload_state",
    response={200: AssetStateSchema},
    **COMMON_ROUTER_SETTINGS,
    include_in_schema=False,  # TODO, should this be advertised?
)
@decorate_view(cache_per_user(DEFAULT_CACHE_SECONDS))
def asset_upload_state(
    request,
    asset: str,
):
    asset = get_asset_by_url(request, asset)
    return asset


@router.get(
    "/{str:userurl}/{str:asseturl}",
    response=AssetSchema,
)
@decorate_view(cache_per_user(DEFAULT_CACHE_SECONDS))
def get_user_asset(
    request,
    userurl: str,
    asseturl: str,
):
    try:
        asset = Asset.objects.get(url=asseturl, owner__url=userurl)
    except Asset.DoesNotExist:
        raise NOT_FOUND
    if asset.visibility not in [PUBLIC, UNLISTED]:
        raise NOT_FOUND
    return asset


# ----------------------------------------------------------------------------
# UPLOADS ENDPOINTS
# (These are duplicated in api.users. Remove the ones defined here after
# blocks/brush refactors have been done. )
# ----------------------------------------------------------------------------


# This endpoint is for internal Open Blocks use for now. It's more complex than
# it needs to be until Open Blocks can send the formats data in a zip or some
# other way.
@router.post(
    "/{str:asset}/blocks_format",
    auth=JWTAuth(),
    response={200: UploadJobSchemaOut},
    include_in_schema=False,  # TODO this route, coupled with finalize_asset
    # has a race condition. If this route becomes public, this will probably
    # need to be fixed.
)
@decorate_view(transaction.atomic)
def add_blocks_asset_format(
    request,
    asset: str,
    files: Optional[List[UploadedFile]] = File(None),
):
    user = request.user
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)

    if request.headers.get("content-type").startswith("multipart/form-data"):
        print("***** REQUEST DEBUG START *****")
        try:
            print("FILES:")
            print(request.FILES)
            queue_blocks_upload_format(user, asset, files)
        except HttpError:
            print("HEADERS:")
            print(request.headers)
            print("POST DATA:")
            print(request.POST)
            raise
    else:
        raise HttpError(415, "Unsupported content type.")

    asset.save()
    return get_publish_url(request, asset)


@router.post(
    "/{str:asset}/blocks_finalize",
    auth=JWTAuth(),
    response={200: UploadJobSchemaOut},
    include_in_schema=False,  # TODO this route has a race condition with
    # add_blocks_asset_format and will overwrite the last format uploaded. If this
    # route becomes public, this will probably need to be fixed.
)
@decorate_view(transaction.atomic)
def finalize_asset(
    request,
    asset: str,
    data: AssetFinalizeData,
):
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)

    queue_finalize_asset(asset.url, data)

    return get_publish_url(request, asset)


@router.post(
    "",
    response={200: UploadJobSchemaOut},
    auth=JWTAuth(),
    include_in_schema=False,
)
@router.post(
    "/",
    response={201: UploadJobSchemaOut},
    auth=JWTAuth(),
    include_in_schema=False,
)
def upload_new_assets(
    request,
    files: Optional[List[UploadedFile]] = File(None),
):
    user = request.user
    owner, _ = AssetOwner.objects.get_or_create(
        django_user=user,
        email=user.email,
        defaults={
            "url": secrets.token_urlsafe(8),
            "displayname": user.displayname,
        },
    )
    job_snowflake = generate_snowflake()
    asset_token = secrets.token_urlsafe(8)
    asset = Asset.objects.create(
        id=job_snowflake,
        url=asset_token,
        owner=owner,
        name="Untitled Asset",
    )
    if files is not None:
        from icosa.helpers.upload import upload_api_asset

        try:
            upload_api_asset(
                asset,
                files,
            )
        except HttpError as err:
            raise err

        # queue_upload_api_asset(
        #     user,
        #     asset,
        #     files,
        # )
    return get_publish_url(request, asset)


def filter_assets(
    filters: AssetFilters,
    assets: QuerySet[Asset] = None,
    q: Q = Q(visibility=PUBLIC),
) -> QuerySet[Asset]:
    if filters.tag:
        q &= Q(tags__name__in=filters.tag)
    if filters.category:
        category_str = filters.category.value.upper()
        category_str = POLY_CATEGORY_MAP.get(category_str, category_str)
        q &= Q(category__iexact=category_str)
    if filters.license:
        q &= filter_license(filters)
    if filters.curated:
        q &= Q(curated=True)
    if filters.name:
        q &= Q(name__icontains=filters.name)
    if filters.description:
        q &= Q(description__icontains=filters.description)
    author_name = filters.authorName or filters.author_name or None
    if author_name is not None:
        q &= Q(owner__displayname__icontains=author_name)
    if filters.format:
        q &= build_format_q(filters.format)
    try:
        keyword_q = get_keyword_q(filters)
    except HttpError:
        raise
    q &= filter_complexity(filters)
    q &= filter_triangle_count(filters)
    q &= filter_zip_archive_url(filters)

    if config.HIDE_REPORTED_ASSETS:
        ex_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED) | Q(last_reported_time__isnull=False)
    else:
        ex_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED)

    # Debug tests:
    # from django.db import connection, reset_queries

    # reset_queries()

    if assets is None:
        assets = Asset.objects.all()

    assets = (
        assets.filter(q, keyword_q)
        .exclude(ex_q)
        .select_related("owner")
        .prefetch_related(
            "resource_set",
            "format_set",
        )
        .distinct()
    )
    # Debug tests:
    # print(assets.explain())
    # _ = list(assets)
    # print(connection.queries)
    # print(len(connection.queries))

    return assets


def sort_assets(key: Order, assets: QuerySet[Asset]) -> QuerySet[Asset]:
    (sort_key, sort_direction) = ORDER_FIELD_MAP.get(key.value)

    if sort_direction == SortDirection.DESC:
        assets = assets.order_by(F(sort_key).desc(nulls_last=True))
    if sort_direction == SortDirection.ASC:
        assets = assets.order_by(F(sort_key).asc(nulls_last=True))
    return assets


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
    filters: AssetFilters = Query(...),
):
    try:
        assets = filter_assets(filters)
    except FilterException as err:
        raise HttpError(400, f"{err}")

    order_by = filters.orderBy or filters.order_by or None
    if order_by is not None:
        assets = sort_assets(order_by, assets)

    return assets
