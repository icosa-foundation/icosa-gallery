import secrets
from typing import List, Optional

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    AssetPagination,
    check_user_owns_asset,
    check_user_owns_asset_collection,
    get_asset_by_url,
    get_publish_url,
)
from icosa.helpers.snowflake import generate_snowflake
from icosa.jwt.authentication import JWTAuth
from icosa.models import PRIVATE, PUBLIC, UNLISTED, Asset, AssetCollection, AssetOwner
from ninja import File, Form, Query, Router
from ninja.decorators import decorate_view
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.pagination import paginate

from .filters import (
    FiltersAsset,
    FiltersOrder,
    FiltersUserAsset,
    filter_and_sort_assets,
)
from .schema import (
    AssetCollectionPostSchema,
    AssetCollectionSchema,
    AssetMetaData,
    AssetSchema,
    AssetSchemaPrivate,
    AssetVisibility,
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
    "/me/assets/{str:asset_url}",
    auth=JWTAuth(),
    response=AssetSchemaPrivate,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def get_asset(
    request,
    asset_url: str,
):
    asset = get_asset_by_url(request, asset_url)
    check_user_owns_asset(request, asset)
    return asset


@router.delete(
    "/me/assets/{str:asset_url}",
    auth=JWTAuth(),
    response={204: int},
)
def delete_asset(
    request,
    asset_url: str,
):
    asset = get_asset_by_url(request, asset_url)
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


@router.get(
    "/me/collections",
    auth=JWTAuth(),
    include_in_schema=False,
    response=List[AssetCollectionSchema],
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
@paginate(AssetPagination)
def get_collections(
    request,
):
    user = request.user
    collections = AssetCollection.objects.filter(user=user)
    return collections


@router.post(
    "/me/collections",
    auth=JWTAuth(),
    include_in_schema=False,
    response=AssetCollectionSchema | int,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def post_collections(
    request,
    data: Form[AssetCollectionPostSchema],
    image: Optional[File[UploadedFile]] = File(None),
):
    user = request.user
    visibility = data.visibility if data.visibility is not None else AssetVisibility.PRIVATE

    if image is not None:
        print(image.file.name)
    # collection = AssetCollection.objects.create(
    #     name=data.name, description=data.description, visibility=visibility, user=user
    # )
    return AssetCollection.objects.first()
    return collection


@router.get(
    "/me/collections/{str:asset_collection_url}",
    auth=JWTAuth(),
    include_in_schema=False,
    response=AssetCollectionSchema,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def get_collection(
    request,
    asset_collection_url: str,
):
    asset_collection = get_object_or_404(AssetCollection, url=asset_collection_url)
    check_user_owns_asset_collection(request, asset_collection)
    return asset_collection
