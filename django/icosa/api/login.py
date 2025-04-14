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
