import re
import secrets
from typing import List, NoReturn, Optional

from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    POLY_CATEGORY_MAP,
    AssetPagination,
)
from icosa.api.authentication import AuthBearer
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import PUBLIC, Asset
from icosa.models import User as IcosaUser
from icosa.tasks import (
    queue_finalize_asset,
    queue_upload_asset,
    queue_upload_format,
)
from ninja import File, Query, Router
from ninja.decorators import decorate_view
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate

from django.conf import settings
from django.core.files.storage import get_storage_class
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.urls import reverse
from django.views.decorators.cache import cache_page

from .schema import (
    AssetFilters,
    AssetFinalizeData,
    AssetSchemaOut,
    UploadJobSchemaOut,
    get_keyword_q,
)

router = Router()

default_storage = get_storage_class()()

DEFAULT_CACHE_SECONDS = 10

IMAGE_REGEX = re.compile("(jpe?g|tiff?|png|webp|bmp)")


def get_publish_url(request, asset: Asset) -> str:
    url = request.build_absolute_uri(
        reverse(
            "publish_asset",
            kwargs={
                "asset_url": asset.url,
            },
        )
    )
    if settings.DEPLOYMENT_HOST_API is not None:
        url = url.replace(
            settings.DEPLOYMENT_HOST_API, settings.DEPLOYMENT_HOST_WEB
        )
    return 200, {
        "publishUrl": url,
        "assetId": asset.url,
    }


def user_can_view_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    if asset.visibility == "PRIVATE":
        return user_owns_asset(request, asset)
    return True


def user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    # This probably needs to be done in from_ninja_request
    # but putting requests stuff in models seemed wrong
    # so probably needs a refactor
    if not hasattr(request, "auth"):
        header = request.headers.get("Authorization")
        if header is None:
            return False
        if not header.startswith("Bearer "):
            return False
        token = header.replace("Bearer ", "")
        user = AuthBearer().authenticate(request, token)
        return (
            user is not None
            and IcosaUser.from_django_user(user) == asset.owner
        )
    return IcosaUser.from_ninja_request(request) == asset.owner


def check_user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> NoReturn:
    if not user_owns_asset(request, asset):
        raise HttpError(404, "Asset not found.")


def get_asset_by_id(
    request: HttpRequest,
    asset: int,
) -> Asset:
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(pk=asset)
    except Asset.DoesNotExist:
        raise HttpError(404, "Asset not found.")
    if not user_can_view_asset(request, asset):
        raise HttpError(404, "Asset not found.")
    return asset


def get_asset_by_url(
    request: HttpRequest,
    asset: str,
) -> Asset:
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(url=asset)
    except Asset.DoesNotExist:
        raise HttpError(404, "Asset not found.")
    if not user_can_view_asset(request, asset):
        if settings.DEBUG:
            raise HttpError(401, "Not authorized.")
        else:
            raise HttpError(404, "Asset not found.")
    return asset


def get_my_id_asset(
    request,
    asset: int,
):
    try:
        asset = get_asset_by_id(request, asset)
    except Exception:
        raise
    check_user_owns_asset(request, asset)
    return asset


@router.get(
    "/{str:asset}",
    response=AssetSchemaOut,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(cache_page(DEFAULT_CACHE_SECONDS))
def get_asset(
    request,
    asset: str,
):
    return get_asset_by_url(request, asset)


# @router.delete(
#     "/{asset}",
#     auth=AuthBearer(),
#     response=AssetSchemaOut,
# )
# def delete_asset(
#     request,
#     asset: int,
# ):
#     asset = get_my_id_asset(request, asset)
#     # TODO(james): do we wait until storages is implemented for this?
#     # Asset removal from storage
#     owner = IcosaUser.from_ninja_request(request)
#     asset_folder = f"{settings.MEDIA_ROOT}/{owner.id}/{asset.id}/"
#     # path = str(Path(asset.thumbnail.name).parent)

#     try:
#         default_storage.delete(asset_folder)
#     except Exception:
#         raise HttpError(
#             status_code=500, detail=f"Failed to remove asset {asset.id}"
#         )
#     asset.delete()
#     return asset


# This endpoint is for internal OpenBrush use for now. It's more complex than
# it needs to  be until OpenBrush can send the formats data in a zip or some
# other way.
@router.post(
    "/{str:asset}/blocks_format",
    auth=AuthBearer(),
    response={200: UploadJobSchemaOut},
    include_in_schema=False,  # TODO this route, coupled with finalize_asset
    # has a race condition. If this route becomes public, this will probably
    # need to be fixed.
)
@decorate_view(transaction.atomic)
def add_asset_format(
    request,
    asset: str,
    files: Optional[List[UploadedFile]] = File(None),
):
    user = IcosaUser.from_ninja_request(request)
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)

    if request.headers.get("content-type").startswith("multipart/form-data"):
        print("***** REQUEST DEBUG START *****")
        try:
            print("FILES:")
            print(request.FILES)
            queue_upload_format(user, asset, files)
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
    auth=AuthBearer(),
    response={200: UploadJobSchemaOut},
    include_in_schema=False,  # TODO this route has a race condition with
    # add_asset_format and will overwrite the last format uploaded. If this
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


@router.patch(
    "/{str:asset}/unpublish",
    auth=AuthBearer(),
    response=AssetSchemaOut,
)
def unpublish_asset(
    request,
    asset: int,
):
    asset = get_my_id_asset(request, asset)
    asset.visibility = "PRIVATE"
    asset.save()
    return asset


@router.get(
    "/{str:userurl}/{str:asseturl}",
    response=AssetSchemaOut,
)
@decorate_view(cache_page(DEFAULT_CACHE_SECONDS))
def get_user_asset(
    request,
    userurl: str,
    asseturl: str,
):
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(url=asseturl, owner__url=userurl)
    except Asset.DoesNotExist:
        raise HttpError(404, "Asset not found.")

    if not user_can_view_asset(request, asset):
        raise HttpError(404, "Asset not found.")
    return asset


@router.post(
    "",
    response={200: UploadJobSchemaOut},
    auth=AuthBearer(),
    include_in_schema=False,
)
@router.post(
    "/",
    response={201: UploadJobSchemaOut},
    auth=AuthBearer(),
    include_in_schema=False,
)
def upload_new_assets(
    request,
    files: Optional[List[UploadedFile]] = File(None),
):
    user = IcosaUser.from_ninja_request(request)
    job_snowflake = generate_snowflake()
    asset_token = secrets.token_urlsafe(8)
    asset = Asset.objects.create(
        id=job_snowflake,
        url=asset_token,
        owner=user,
        name="Untitled Asset",
    )
    if files is not None:
        queue_upload_asset(
            user,
            asset,
            files,
        )
    return get_publish_url(request, asset)


@router.get(
    "",
    response=List[AssetSchemaOut],
    **COMMON_ROUTER_SETTINGS,
)
@router.get(
    "/",
    response=List[AssetSchemaOut],
    include_in_schema=False,
    **COMMON_ROUTER_SETTINGS,
)
@paginate(AssetPagination)
@decorate_view(cache_page(DEFAULT_CACHE_SECONDS))
def get_assets(
    request,
    filters: AssetFilters = Query(...),
):
    q = Q(
        visibility=PUBLIC,
        # imported=True,
    )
    ex_q = Q()

    if filters.tag:
        q &= Q(tags__name__in=filters.tag)
    if filters.category:
        category_str = filters.category.upper()
        category_str = POLY_CATEGORY_MAP.get(category_str, category_str)
        q &= Q(category__iexact=category_str)
    if filters.curated:
        q &= Q(curated=True)
    if filters.name:
        q &= Q(name__icontains=filters.name)
    if filters.description:
        q &= Q(description__icontains=filters.description)
    author_name = filters.authorName or filters.author_name or None
    if author_name is not None:
        q &= Q(owner__displayname__icontains=author_name)
    # TODO: orderBy
    if filters.format:
        q &= Q(polyformat__format_type=filters.format)
    try:
        keyword_q = get_keyword_q(filters)
    except HttpError:
        raise

    assets = Asset.objects.filter(q, keyword_q).exclude(ex_q).distinct()

    return assets
