import secrets
import string
from datetime import datetime, timedelta
from typing import List, Optional

from icosa.models import Asset, DeviceCode, Tag, User
from ninja import Query, Router
from ninja.errors import HttpError

from django.db.models import Q

from .authentication import AuthBearer
from .schema import (
    AssetFilters,
    AssetSchemaOut,
    DeviceCodeSchema,
    FullUserSchema,
    PatchUserSchema,
)

router = Router()


def generate_code(length=5):
    # Define a string of characters to exclude
    exclude = "I1O0"
    characters = "".join(
        set(string.ascii_uppercase + string.digits) - set(exclude)
    )
    return "".join(secrets.choice(characters) for i in range(length))


@router.get(
    "/me",
    auth=AuthBearer(),
    response=FullUserSchema,
)
def get_users_me(request):
    return User.from_ninja_request(request)


@router.patch(
    "/me",
    auth=AuthBearer(),
    response=FullUserSchema,
)
def update_user(
    request,
    patch_user: PatchUserSchema,
):
    current_user = User.from_ninja_request(request)
    url = getattr(patch_user, "url", "").strip() or current_user.url

    if (
        User.objects.filter(url__iexact=url).count() != 0
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
    "/me/devicecode",
    auth=AuthBearer(),
    response=DeviceCodeSchema,
)
def get_users_device_code(
    request,
):
    current_user = User.from_ninja_request(request)
    if current_user is not None:
        code = generate_code()
        expiry_time = datetime.utcnow() + timedelta(minutes=1)

        # Delete all codes for this user
        DeviceCode.objects.filter(user=current_user).delete()
        # Delete all expired codes for any user
        DeviceCode.objects.filter(expiry__lt=datetime.utcnow()).delete()

        foo = DeviceCode.objects.create(
            user=current_user,
            devicecode=code,
            expiry=expiry_time,
        )
        print(foo)

        return {"deviceCode": code}
    # headers={"WWW-Authenticate": "Bearer"},
    raise HttpError(401, "Authentication failed.")


@router.get(
    "/me/assets",
    auth=AuthBearer(),
    response=List[AssetSchemaOut],
)
def get_me_assets(request):
    return Asset.objects.filter(user=User.from_ninja_request(request))


@router.get(
    "/me/likedassets",
    auth=AuthBearer(),
    response=List[AssetSchemaOut],
)
def get_me_likedassets(
    request,
    format: Optional[str] = None,
    orderBy: Optional[str] = None,
    filters: AssetFilters = Query(...),
    results: int = 20,
    page: int = 0,
):
    owner = User.from_ninja_request(request)
    liked_assets = owner.userassetlike_set.all()
    q = Q(visibility="PUBLIC")
    if format:
        q &= Q(formats__contains=[{"format": format}])

    if orderBy and orderBy == "LIKED_TIME":
        liked_assets = liked_assets.order_by("-date_liked")

    # Get the ordered IDs for sorting later, if we need to. We can't use
    # `owner.likes.all` because we need the timestamp of when the asset was
    # liked.
    liked_ids = list(liked_assets.values_list("asset__pk", flat=True))
    q &= Q(pk__in=liked_ids)

    if filters.tag:
        tags = Tag.objects.filter(name__in=filters.tag)
        q &= Q(tags__in=tags)

    assets = Asset.objects.filter(q)
    if orderBy and orderBy == "LIKED_TIME":
        # Sort the assets by order of liked ID. Slow, but database-agnostic.
        # Postgres and MySql have different ways to do this, and we'd need to
        # use the `extra` params in our query, which are database-specific.
        assets = sorted(assets, key=lambda i: liked_ids.index(i.pk))
    return assets
