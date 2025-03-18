from ninja import Router
from ninja.errors import HttpError
from ninja_jwt.tokens import RefreshToken

from django.conf import settings
from django.utils import timezone

from ..models import DeviceCode
from .auth import UserAPIKeyAuth
from .schema import LoginToken

router = Router()


@router.post("/device_login", response=LoginToken)
def device_login(request, device_code: str):
    try:
        valid_code = DeviceCode.objects.get(
            devicecode__iexact=device_code,
            expiry__gt=timezone.now(),
        )
        refresh = RefreshToken.for_user(valid_code.user)

        valid_code.delete()
        return {
            "access_token": str(refresh.access_token),
            "token_type": "bearer",
        }

    except (
        DeviceCode.DoesNotExist,
        DeviceCode.MultipleObjectsReturned,
    ):
        # headers={"WWW-Authenticate": "Bearer"},
        raise HttpError(401, "Authentication failed.")


@router.post("/apikey_login", auth=UserAPIKeyAuth(), response=LoginToken)
def apikey_login(request):

    refresh = RefreshToken.for_user(request.auth)
    return {
        "access_token": str(refresh.access_token),
        "token_type": "bearer",
    }
