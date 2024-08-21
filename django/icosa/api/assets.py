import re
from typing import List, NoReturn, Optional

from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    POLY_CATEGORY_MAP,
    AssetPagination,
)
from icosa.api.authentication import AuthBearer
from icosa.helpers.file import upload_asset, upload_format
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import PUBLIC, Asset, PolyFormat, Tag
from icosa.models import User as IcosaUser
from ninja import File, Query, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate

from django.core.files.storage import get_storage_class
from django.db.models import Q
from django.http import HttpRequest
from django.urls import reverse

from .authentication import AuthBearer
from .schema import (
    AssetFilters,
    AssetSchemaOut,
    UploadJobSchemaOut,
    get_keyword_q,
)

router = Router()

default_storage = get_storage_class()()

IMAGE_REGEX = re.compile("(jpe?g|tiff?|png|webp|bmp)")


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
    "/{str:asset}/format",
    auth=AuthBearer(),
    response={201: str},
    include_in_schema=False,
)
def add_asset_format(
    request,
    asset: str,
    files: Optional[List[UploadedFile]] = File(None),
):
    print("***** REQUEST DEBUG START *****")
    print("HEADERS:")
    print(request.headers)
    print("POST DATA:")
    print(request.POST)
    print("FILES:")
    print(request.FILES)
    print("ASSET:")
    print(asset)
    print("***** REQUEST DEBUG END *****")
    user = IcosaUser.from_ninja_request(request)
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)

    if request.headers.get("content-type").startswith("multipart/form-data"):
        try:
            upload_format(user, asset, files)
        except HttpError:
            raise
    else:
        raise HttpError(415, "Unsupported content type.")

    asset.save()
    return 201, "ok"


@router.post(
    "/{str:asset}/finalize",
    auth=AuthBearer(),
    response=AssetSchemaOut,
    include_in_schema=False,
)
def finalize_asset(
    request,
    asset: str,
):
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)
    # TODO(james): This can probably be done in one query
    resources = asset.polyresource_set.filter(file="")
    format_pks = list(set([x.format.pk for x in resources]))
    formats = PolyFormat.objects.filter(pk__in=format_pks)
    formats.delete()
    return asset


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
    response={201: UploadJobSchemaOut},
    auth=AuthBearer(),
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
    try:
        asset = upload_asset(
            user,
            job_snowflake,
            files,
            None,
        )
    except HttpError:
        raise
    return 201, {
        "upload_job": job_snowflake,
        "edit_url": request.build_absolute_uri(
            reverse(
                "edit_asset",
                kwargs={
                    "user_url": user.url,
                    "asset_url": asset.url,
                },
            )
        ),
    }


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
        tags = Tag.objects.filter(name__in=filters.tag)
        q &= Q(tags__in=tags)
    if filters.category:
        # Categories are a special enum. I've elected to ingnore any categories
        # that do not match. I could as easily return zero results for
        # non-matches. I've also assumed that OpenBrush hands us uppercase
        # strings, but I could be wrong.
        category_str = filters.category
        if category_str.upper() in POLY_CATEGORY_MAP.keys():
            category_str = POLY_CATEGORY_MAP[category_str]
        q &= Q(tags__name__iexact=category_str)
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
        q &= Q(polyresource__format__format_type=filters.format)
    try:
        keyword_q = get_keyword_q(filters)
    except HttpError:
        raise

    assets = Asset.objects.filter(q, keyword_q).exclude(ex_q).distinct()

    return assets
