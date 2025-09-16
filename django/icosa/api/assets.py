import re
import secrets
from typing import List, Optional

from constance import config
from django.db import transaction
from django.db.models import Q
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    DEFAULT_CACHE_SECONDS,
    NOT_FOUND,
    AssetPagination,
    check_user_owns_asset,
    get_asset_by_url,
    get_publish_url,
)
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

from .filters import (
    AssetFilters,
    OrderFilter,
    filter_and_sort_assets,
)
from .schema import (
    AssetFinalizeData,
    AssetSchema,
    AssetStateSchema,
    UploadJobSchemaOut,
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
    order: OrderFilter = Query(...),
    filters: AssetFilters = Query(...),
):
    exc_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED)
    if config.HIDE_REPORTED_ASSETS:
        exc_q = Q(license__isnull=True) | Q(license=ALL_RIGHTS_RESERVED) | Q(last_reported_time__isnull=False)

    assets = filter_and_sort_assets(
        filters,
        order,
        assets=Asset.objects.all(),
        exc_q=exc_q,
    )

    return assets
