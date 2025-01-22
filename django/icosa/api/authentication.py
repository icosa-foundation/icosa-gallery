from datetime import datetime, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from ninja.errors import HttpError
from ninja.security import HttpBearer

ALGORITHM = "HS256"


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        authentication_error = HttpError(401, "Invalid Credentials")
        try:
            payload = jwt.decode(
                token,
                settings.JWT_KEY,
                algorithms=[ALGORITHM],
            )
            username: str = payload.get("sub")
            if username is None:
                # headers={"WWW-Authenticate": "Bearer"},
                raise authentication_error
        except jwt.PyJWTError:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        try:
            user = User.objects.get(email=username)
        except User.MultipleObjectsReturned:
            # headers={"WWW-Authenticate": "Bearer"},
            # TODO: or do we want to return the first that we find?
            raise authentication_error
        if user is None:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error

        return user
