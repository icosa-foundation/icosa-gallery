from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from ..models import AssetOwner, DeviceCode
from .schema import LoginToken

router = Router()


@router.post("/device_login", response=LoginToken)
def device_login(request, device_code: str):
    try:
        valid_code = DeviceCode.objects.get(
            devicecode__iexact=device_code,
            expiry__gt=timezone.now(),
        )
        # We might be able to avoid using from_django_user here if the token
        # generation is instead called from the django user we have. This is
        # how this code originally worked after the abstract user feature was
        # merged in.
        asset_owner = AssetOwner.from_django_user(valid_code.user)
        access_token = asset_owner.generate_access_token()

        valid_code.delete()
        return {
            "access_token": str(access_token),
            "token_type": "bearer",
        }

    except (
        DeviceCode.DoesNotExist,
        DeviceCode.MultipleObjectsReturned,
    ):
        # headers={"WWW-Authenticate": "Bearer"},
        raise HttpError(401, "Authentication failed.")
