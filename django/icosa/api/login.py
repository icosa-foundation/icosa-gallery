from datetime import datetime, timedelta

from icosa.models import DeviceCode
from ninja import Router
from ninja.errors import HttpError

from django.conf import settings

from .authentication import create_access_token
from .schema import LoginToken

router = Router()


@router.post("/device_login", response=LoginToken)
def device_login(request, device_code: str):
    try:
        valid_code = DeviceCode.objects.get(
            devicecode__iexact=device_code,
            expiry__gt=datetime.utcnow(),
        )
        access_token_expires = timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        access_token = create_access_token(
            data={"sub": valid_code.user.email},
            expires_delta=access_token_expires,
        )
        valid_code.delete()
        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    except (
        DeviceCode.DoesNotExist,
        DeviceCode.MultipleObjectsReturned,
    ):
        # headers={"WWW-Authenticate": "Bearer"},
        raise HttpError(401, "Authentication failed.")
