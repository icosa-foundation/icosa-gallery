import secrets
from typing import List, Optional

from django.db import transaction
from django.db.models import Q
from django.views.decorators.cache import never_cache
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    POLY_CATEGORY_MAP,
    AssetPagination,
    build_format_q,
    check_user_owns_asset,
    get_asset_by_url,
    get_publish_url,
)
from icosa.api.assets import filter_assets, sort_assets
from icosa.api.exceptions import FilterException
from icosa.helpers.snowflake import generate_snowflake
from icosa.jwt.authentication import JWTAuth
from icosa.models import (
    PRIVATE,
    PUBLIC,
    UNLISTED,
    Asset,
    AssetOwner,
    Tag,
)
from icosa.tasks import queue_blocks_upload_format, queue_finalize_asset
from ninja import File, Query, Router
from ninja.decorators import decorate_view
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate

from .schema import (
    AssetFilters,
    AssetFinalizeData,
    AssetSchema,
    AssetSchemaWithState,
    FullUserSchema,
    PatchUserSchema,
    UploadJobSchemaOut,
    UserAssetFilters,
    get_keyword_q,
)

router = Router()


@router.get(
    "/me",
    auth=JWTAuth(),
    response=FullUserSchema,
)
@decorate_view(never_cache)
def get_users_me(request):
    return request.user


@router.patch(
    "/me",
    auth=JWTAuth(),
    response=FullUserSchema,
)
@decorate_view(never_cache)
def update_user(
    request,
    patch_user: PatchUserSchema,
):
    current_user = request.user
    url = getattr(patch_user, "url", "").strip() or current_user.url

    if AssetOwner.objects.filter(url__iexact=url).count() != 0 and url != current_user.url:
        # Used to return 403. James believes this is the wrong status code.
        # Better to use Unprocessable Entity.
        raise HttpError(422, "This URL is already in use")
    for key, value in patch_user.__dict__.items():
        if getattr(patch_user, key, None) is not None:
            setattr(current_user, key, value)
    current_user.save()
    return current_user


@router.get(
    "/me/assets",
    auth=JWTAuth(),
    response=List[AssetSchema],
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
@paginate(AssetPagination)
def get_me_assets(
    request,
    filters: UserAssetFilters = Query(...),
):
    # TODO(james): Standardise this with /me/likedassets
    user = request.user
    q = Q(
        owner__django_user=user,
    )
    ex_q = Q()
    if filters.visibility:
        if filters.visibility in [
            PRIVATE,
            UNLISTED,
        ]:
            q &= Q(visibility=filters.visibility)
        elif filters.visibility == "PUBLISHED":
            q &= Q(visibility=PUBLIC)
        elif filters.visibility == "UNSPECIFIED":
            pass
        else:
            raise HttpError(
                400,
                "Unknown visibility specifier. Expected one of UNSPECIFIED, PUBLISHED, PRIVATE, UNLISTED.",  # TODO: brittle
            )

    if filters.format:
        q &= build_format_q(filters.format)

    if filters.tag:
        tags = Tag.objects.filter(name__in=filters.tag)
        q &= Q(tags__in=tags)
    if filters.category:
        category_str = filters.category.value.upper()
        category_str = POLY_CATEGORY_MAP.get(category_str, category_str)
        q &= Q(category__iexact=category_str)
    if filters.curated:
        q &= Q(curated=True)
    if filters.name:
        q &= Q(name__icontains=filters.name)
    if filters.description:
        q &= Q(description__icontains=filters.description)
    try:
        keyword_q = get_keyword_q(filters)
    except HttpError:
        raise
    # TODO: orderBy
    assets = (
        Asset.objects.filter(q, keyword_q)
        .exclude(ex_q)
        .distinct()
        .select_related("owner")
        .prefetch_related(
            "format_set",
            "resource_set",
        )
        .prefetch_related("tags")
    )
    return assets


@router.post(
    "/me/assets",
    response={201: UploadJobSchemaOut},
    auth=JWTAuth(),
    include_in_schema=False,
)
@decorate_view(never_cache)
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
    return get_publish_url(request, asset, 201)


@router.get(
    "/me/assets/{str:asset}",
    auth=JWTAuth(),
    response=AssetSchemaWithState,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def get_me_asset(
    request,
    asset: str,
):
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)
    return asset


@router.delete(
    "/me/assets/{str:asset}",
    auth=JWTAuth(),
    response={204: int},
)
def delete_asset(
    request,
    asset: str,
):
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)
    with transaction.atomic():
        asset.hide_media()
        asset.delete()
    return 204


@router.get(
    "/me/likedassets",
    auth=JWTAuth(),
    response=List[AssetSchema],
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
@paginate(AssetPagination)
def get_me_likedassets(
    request,
    filters: AssetFilters = Query(...),
):
    user = request.user
    assets = Asset.objects.filter(id__in=user.likedassets.all().values_list("asset__id", flat=True))
    q = Q(
        visibility__in=[PUBLIC, UNLISTED],
    )
    q |= Q(visibility__in=[PRIVATE, UNLISTED], owner__django_user=user)

    try:
        assets = filter_assets(filters, assets, q)
    except FilterException as err:
        raise HttpError(400, f"{err}")

    if filters.orderBy:
        assets = sort_assets(filters.orderBy, assets)

    return assets


# ----------------------------------------------------------------------------
# UPLOADS ENDPOINTS
# (These are duplicated in api.assets. Remove the ones defined over there after
# blocks/brush refactors have been done. )
# ----------------------------------------------------------------------------


# This endpoint is for internal Open Blocks use for now. It's more complex than
# it needs to be until Open Blocks can send the formats data in a zip or some
# other way.
@router.post(
    "/me/assets/{str:asset}/blocks_format",
    auth=JWTAuth(),
    response={200: UploadJobSchemaOut},
    include_in_schema=False,  # TODO this route, coupled with finalize_asset
    # has a race condition. If this route becomes public, this will probably
    # need to be fixed.
)
@decorate_view(never_cache)
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
        try:
            queue_blocks_upload_format(user, asset, files)
        except HttpError:
            raise
    else:
        raise HttpError(415, "Unsupported content type.")

    asset.save()
    return get_publish_url(request, asset)


@router.post(
    "/me/assets/{str:asset}/blocks_finalize",
    auth=JWTAuth(),
    response={200: UploadJobSchemaOut},
    include_in_schema=False,  # TODO this route has a race condition with
    # add_blocks_asset_format and will overwrite the last format uploaded. If this
    # route becomes public, this will probably need to be fixed.
)
@decorate_view(never_cache)
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
