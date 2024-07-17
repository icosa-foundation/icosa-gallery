import re
from typing import List, NoReturn

from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    POLY_CATEGORY_MAP,
    AssetPagination,
)
from icosa.helpers.file import upload_asset
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import PUBLIC, Asset, Tag
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
from .schema import AssetFilters, AssetSchemaOut, UploadJobSchemaOut

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
    if (
        request.auth.is_anonymous
        or IcosaUser.from_ninja_request(request) != asset.owner
    ):
        return False
    return True


def check_user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> NoReturn:
    if not user_owns_asset(request, asset):
        raise HttpError(403, "Unauthorized user.")


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
    "/{asset}",
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


# TODO(james): do we wait until storages is implemented for this?
# @router.patch(
#     "/{asset}",
#     auth=AuthBearer(),
#     response_model=Asset,
# )
# def update_asset(
#     request
#     background_tasks: BackgroundTasks,
#     request: Request,
#     asset: int,
#     data: Optional[AssetPatchData] = None,
#     name: Optional[str] = Form(None),
#     url: Optional[str] = Form(None),
#     description: Optional[str] = Form(None),
#     visibility: Optional[str] = Form(None),
#     current_user: User = Depends(get_current_user),
#     thumbnail: Optional[UploadedFile] = File(None),
# ):
#     current_asset = _DBAsset(**(await get_my_id_asset(asset, current_user)))

#     if request.headers.get("content-type") == "application/json":
#         update_data = data.dict(exclude_unset=True)
#     elif request.headers.get("content-type").startswith("multipart/form-data"):
#         update_data = {
#             k: v
#             for k, v in {
#                 "name": name,
#                 "url": url,
#                 "description": description,
#                 "visibility": visibility,
#             }.items()
#             if v is not None
#         }
#     else:
#         raise HTTPException(
#             status_code=415, detail="Unsupported content type."
#         )

#     updated_asset = current_asset.copy(update=update_data)
#     updated_asset.id = int(updated_asset.id)
#     updated_asset.owner = int(updated_asset.owner)
#     query = assets.update(None)
#     query = query.where(assets.c.id == updated_asset.id)
#     query = query.values(updated_asset.dict())
#     await database.execute(query)
#     if thumbnail:
#         background_tasks.add_task(
#             upload_thumbnail_background, current_user, thumbnail, asset
#         )
#     return await get_my_id_asset(asset, current_user)


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
    "/{str:userurl}/{asseturl}",
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
    files: List[UploadedFile] = File(...),
):
    user = IcosaUser.from_ninja_request(request)
    if len(files) == 0:
        raise HttpError(422, "No files provided.")
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
        if filters.format == "BLOCKS":
            q &= Q(
                polyresource__format__format_type__in=[
                    "GLTF",
                    "GLTF2",
                ]
            )
            ex_q &= Q(polyresource__format__format_type="TILT")
        else:
            q &= Q(polyresource__format__format_type=filters.format)
    keyword_q = Q()
    if filters.keywords:
        # TODO: should we limit the number of possible keywords?
        # If so, do we truncate silently, or error?
        for keyword in filters.keywords.split(" "):
            keyword_q &= (
                Q(description__icontains=keyword)
                | Q(name__icontains=keyword)
                | Q(tags__name__icontains=keyword)
            )

    assets = Asset.objects.filter(q, keyword_q).exclude(ex_q).distinct()

    return assets
