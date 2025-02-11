from typing import List

from django.db.models import Q
from icosa.api import (
    COMMON_ROUTER_SETTINGS,
    POLY_CATEGORY_MAP,
    AssetPagination,
    build_format_q,
)
from icosa.api.assets import filter_assets, sort_assets
from icosa.api.exceptions import FilterException
from icosa.models import PRIVATE, PUBLIC, UNLISTED, Asset, AssetOwner, Tag
from ninja import Query, Router
from ninja.errors import HttpError
from ninja.pagination import paginate

from .authentication import AuthBearer
from .schema import (
    AssetFilters,
    AssetSchema,
    FullUserSchema,
    PatchUserSchema,
    UserAssetFilters,
    get_keyword_q,
)

router = Router()


@router.get(
    "/me",
    auth=AuthBearer(),
    response=FullUserSchema,
)
def get_users_me(request):
    return AssetOwner.from_ninja_request(request)


@router.patch(
    "/me",
    auth=AuthBearer(),
    response=FullUserSchema,
)
def update_user(
    request,
    patch_user: PatchUserSchema,
):
    current_user = AssetOwner.from_ninja_request(request)
    url = getattr(patch_user, "url", "").strip() or current_user.url

    if (
        AssetOwner.objects.filter(url__iexact=url).count() != 0
        and url != current_user.url
    ):
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
    auth=AuthBearer(),
    response=List[AssetSchema],
    **COMMON_ROUTER_SETTINGS,
)
@paginate(AssetPagination)
def get_me_assets(
    request,
    filters: UserAssetFilters = Query(...),
):
    owner = AssetOwner.from_ninja_request(request)
    q = Q(
        owner=owner,
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
        category_str = filters.category.upper()
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
        .prefetch_related("format_set")
        .prefetch_related("tags")
    )
    return assets


@router.get(
    "/me/likedassets",
    auth=AuthBearer(),
    response=List[AssetSchema],
    **COMMON_ROUTER_SETTINGS,
)
@paginate(AssetPagination)
def get_me_likedassets(
    request,
    filters: AssetFilters = Query(...),
):
    owner = AssetOwner.from_ninja_request(request)
    assets = owner.likedassets.all()
    q = Q(
        visibility__in=[PUBLIC, UNLISTED],
    )
    q |= Q(visibility__in=[PRIVATE, UNLISTED], owner=owner)

    try:
        assets = filter_assets(filters)
    except FilterException as err:
        raise HttpError(400, f"{err}")

    if filters.orderBy:
        assets = sort_assets(filters.orderBy, assets)

    return assets
