import secrets
from typing import List, Optional

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    AssetCollectionPagination,
    AssetPagination,
    check_user_owns_asset,
    get_asset_by_url,
    get_publish_url,
)
from icosa.helpers.file import validate_mime
from icosa.helpers.snowflake import generate_snowflake
from icosa.jwt.authentication import JWTAuth
from icosa.models import (
    PRIVATE,
    PUBLIC,
    UNLISTED,
    VALID_THUMBNAIL_MIME_TYPES,
    Asset,
    AssetCollection,
    AssetOwner,
)
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
    AssetCollectionPutSchema,
    AssetCollectionSchema,
    AssetCollectionSchemaWithRejections,
    AssetMetaData,
    AssetSchema,
    AssetSchemaPrivate,
    AssetVisibility,
    Error,
    FullUserSchema,
    ImageSchema,
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
def show_my_user(request):
    return request.user


@router.patch(
    "/me",
    auth=JWTAuth(),
    response=FullUserSchema,
)
@decorate_view(never_cache)
def update_my_user(
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
def list_my_assets(
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
    auth=JWTAuth()
)
@decorate_view(never_cache)
def create_a_new_asset(
    request,
    data: Form[AssetMetaData],
    files: Optional[List[UploadedFile]] = None,
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
def show_an_asset(
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
def delete_an_asset(
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
def list_my_likedassets(
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
    response=List[AssetCollectionSchema],
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
@paginate(AssetCollectionPagination)
def get_my_collections(
    request,
):
    user = request.user
    collections = AssetCollection.objects.filter(user=user)
    return collections


@router.post(
    "/me/collections",
    auth=JWTAuth(),
    response={201: AssetCollectionSchemaWithRejections, 400: Error},
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def create_a_collection(
    request,
    data: AssetCollectionPostSchema,
):
    user = request.user
    visibility = data.visibility if data.visibility is not None else AssetVisibility.PRIVATE.value

    assets = Asset.objects.none()
    rejected_asset_urls = []
    if data.asset_url is not None:
        urls = []
        for url in data.asset_url:
            if Asset.objects.filter(url=url, visibility=PUBLIC).exists():
                urls.append(url)
            else:
                rejected_asset_urls.append(url)
        assets = Asset.objects.filter(url__in=urls)

    collection = AssetCollection.objects.create(
        name=data.name, description=data.description, visibility=visibility, user=user
    )
    for asset in assets:
        collection.assets.add(asset)

    return 201, {"collection": collection, "rejectedAssetUrls": rejected_asset_urls if rejected_asset_urls else None}


@router.get(
    "/me/collections/{str:asset_collection_url}",
    auth=JWTAuth(),
    response=AssetCollectionSchema,
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def show_a_collection(
    request,
    asset_collection_url: str,
):
    user = request.user
    asset_collection = get_object_or_404(AssetCollection, url=asset_collection_url, user=user)
    return asset_collection


@router.patch(
    "/me/collections/{str:asset_collection_url}",
    auth=JWTAuth(),
    response={200: AssetCollectionSchemaWithRejections, 400: Error},
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def update_a_collection(
    request,
    asset_collection_url: str,
    data: AssetCollectionPostSchema,
):
    user = request.user
    collection = get_object_or_404(AssetCollection, url=asset_collection_url, user=user)
    filtered_data = data.dict(exclude_unset=True)
    for attr, value in filtered_data.items():
        setattr(collection, attr, value)
    collection.save()

    assets = Asset.objects.none()
    rejected_asset_urls = []
    if data.asset_url is not None:
        urls = []
        for url in data.asset_url:
            if Asset.objects.filter(url=url, visibility=PUBLIC).exists():
                urls.append(url)
            else:
                rejected_asset_urls.append(url)
        assets = Asset.objects.filter(url__in=urls)
    for asset in assets:
        collection.assets.add(asset)

    return 200, {"collection": collection, "rejectedAssetUrls": rejected_asset_urls if rejected_asset_urls else None}


@router.put(
    "/me/collections/{str:asset_collection_url}/set_assets",
    auth=JWTAuth(),
    response={200: AssetCollectionSchemaWithRejections, 400: Error},
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def overwrite_assets_for_a_collection(
    request,
    asset_collection_url: str,
    data: AssetCollectionPutSchema,
):
    user = request.user
    collection = get_object_or_404(AssetCollection, url=asset_collection_url, user=user)
    for asset in collection.assets.all():
        collection.assets.remove(asset)

    assets = Asset.objects.none()
    rejected_asset_urls = []
    if data.asset_url is not None:
        urls = []
        for url in data.asset_url:
            if Asset.objects.filter(url=url, visibility=PUBLIC).exists():
                urls.append(url)
            else:
                rejected_asset_urls.append(url)
        assets = Asset.objects.filter(url__in=urls)
    for asset in assets:
        collection.assets.add(asset)

    collection.save()
    return 200, {"collection": collection, "rejectedAssetUrls": rejected_asset_urls if rejected_asset_urls else None}


@router.delete(
    "/me/collections/{str:asset_collection_url}",
    auth=JWTAuth(),
    response={204: int},
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def delete_a_collection(
    request,
    asset_collection_url: str,
):
    user = request.user
    asset_collection = get_object_or_404(AssetCollection, url=asset_collection_url, user=user)
    asset_collection.delete()
    return 204


@router.post(
    "/me/collections/{str:asset_collection_url}/set_thumbnail",
    auth=JWTAuth(),
    response={201: ImageSchema, 400: Error},
    **COMMON_ROUTER_SETTINGS,
)
@decorate_view(never_cache)
def set_an_image_for_a_collection(
    request,
    asset_collection_url: str,
    image: File[UploadedFile],
):
    user = request.user
    asset_collection = get_object_or_404(AssetCollection, url=asset_collection_url, user=user)
    magic_bytes = next(image.chunks(chunk_size=2048))
    image.seek(0)
    if not validate_mime(magic_bytes, VALID_THUMBNAIL_MIME_TYPES):
        return 400, {"message", "Thumbnail must be png or jpg."}
    asset_collection.image = image
    asset_collection.save()
    return 201, {"url": asset_collection.image}
