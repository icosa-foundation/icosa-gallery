from typing import List, Optional

from icosa.models import Asset, User
from ninja import Router

from django.db.models import Q

from .authentication import AuthBearer
from .schema import AssetSchemaOut, FullUser

router = Router()


@router.get("/me", auth=AuthBearer(), response=FullUser)
def get_users_me(request):
    return User.from_ninja_request(request)


@router.get(
    "/me/likedassets",
    auth=AuthBearer(),
    response=List[AssetSchemaOut],
)
def get_me_likedassets(
    request,
    format: Optional[str] = None,
    orderBy: Optional[str] = None,
    results: int = 20,
    page: int = 0,
):
    owner = User.from_ninja_request(request)
    liked_assets = owner.userassetlike_set.all()
    q = Q()
    if format:
        q &= Q(formats__contains=[{"format": format}])

    if orderBy and orderBy == "LIKED_TIME":
        liked_assets = liked_assets.order_by("-date_liked")

    # Get the ordered IDs for sorting later, if we need to. We can't use
    # `owner.likes.all` because we need the timestamp of when the asset was
    # liked.
    liked_ids = list(liked_assets.values_list("asset__pk", flat=True))
    assets = Asset.objects.filter(pk__in=liked_ids)

    assets.filter(q)
    if orderBy and orderBy == "LIKED_TIME":
        # Sort the assets by order of liked ID. Slow, but database-agnostic.
        # Postgres and MySql have different ways to do this, and we'd need to
        # use the `extra` params in our query, which are database-specific.
        assets = sorted(assets, key=lambda i: liked_ids.index(i.pk))
    return assets
