import secrets
from typing import List, Optional

from ninja import File, Form, Query, Router
from ninja.decorators import decorate_view
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate

from django.db import transaction
from django.db.models import Q
from django.views.decorators.cache import never_cache
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    AssetPagination,
    check_user_owns_asset,
    get_asset_by_url,
    get_publish_url,
)
from icosa.helpers.snowflake import generate_snowflake
from icosa.jwt.authentication import JWTAuth
from icosa.models import (
    PRIVATE,
    PUBLIC,
    UNLISTED,
    Asset,
    AssetOwner,
)
from icosa.tasks import queue_blocks_upload_format, queue_finalize_asset

from .filters import (
    FiltersAsset,
    FiltersOrder,
    FiltersUserAsset,
    filter_and_sort_assets,
)
from .schema import (
    AssetMetaData,
    AssetSchema,
    AssetSchemaPrivate,
    FullUserSchema,
    PatchUserSchema,
    UploadJobSchemaOut,
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
    user = request.user
    if not user.has_single_owner:
        # TODO: handle multiple owners.
        raise HttpError(422, "Cannot identify which owner to update.")
    owner = user.assetowner_set.first()
    url = getattr(patch_user, "url", "").strip() or owner.url

    if AssetOwner.objects.filter(url__iexact=url).exclude(django_user=user).exists() and url != owner.url:
        raise HttpError(422, "This URL is already in use")
    if getattr(patch_user, "displayName", None) is not None:
        display_name = patch_user.displayName
        user.displayname = display_name
        owner.displayname = display_name
    if getattr(patch_user, "url", None) is not None:
        owner.url = patch_user.url
    if getattr(patch_user, "description", None) is not None:
        owner.description = patch_user.description
    user.save()
    owner.save()
    return user


@router.get(
    "/me/assets",
    auth=JWTAuth(),
    response=List[AssetSchemaPrivate],
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
@paginate(AssetPagination)
def get_assets(
    request,
    filters: FiltersUserAsset = Query(...),
    order: FiltersOrder = Query(...),
):
    user = request.user
    inc_q = Q(
        owner__django_user=user,
    )
    assets = filter_and_sort_assets(
        filters,
        order,
        assets=Asset.objects.all(),
        inc_q=inc_q,
    )
    return assets


@router.post(
    "/me/assets",
    response={201: UploadJobSchemaOut},
    auth=JWTAuth(),
    include_in_schema=False,
)
@decorate_view(never_cache)
def new_asset(
    request,
    data: Form[AssetMetaData],
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
                data,
                files,
            )
        except HttpError as err:
            raise err

        # queue_upload_api_asset(
        #     user,
        #     asset,
        #     data,
        #     files,
        # )
    return get_publish_url(request, asset, 201)


@router.get(
    "/me/assets/{str:asset}",
    auth=JWTAuth(),
    response=AssetSchemaPrivate,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def get_asset(
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
def get_likedassets(
    request,
    filters: FiltersAsset = Query(...),
    order: FiltersOrder = Query(...),
):
    user = request.user
    assets = Asset.objects.filter(
        id__in=user.likedassets.all().values_list(
            "asset__id",
            flat=True,
        )
    )
    inc_q = Q(
        visibility__in=[PUBLIC, UNLISTED],
    )
    inc_q |= Q(visibility__in=[PRIVATE, UNLISTED], owner__django_user=user)

    assets = filter_and_sort_assets(
        filters,
        order,
        assets=assets,
        inc_q=inc_q,
    )
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
    data: AssetMetaData,
):
    asset = get_asset_by_url(request, asset)
    check_user_owns_asset(request, asset)

    queue_finalize_asset(asset.url, data)

    return get_publish_url(request, asset)
