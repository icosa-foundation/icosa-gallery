import jwt
from icosa.models import User
from ninja.errors import HttpError
from ninja.security import HttpBearer

from django.conf import settings

ALGORITHM = "HS256"


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(
                token, settings.JWT_KEY, algorithms=[ALGORITHM]
            )
            username: str = payload.get("sub")
            if username is None:
                # headers={"WWW-Authenticate": "Bearer"},
                raise HttpError(401, "Invalid Credentials")
        except jwt.PyJWTError:
            # headers={"WWW-Authenticate": "Bearer"},
            raise HttpError(401, "Invalid Credentials")
        user = User.objects.get(email=username)
        if user is None:
            # headers={"WWW-Authenticate": "Bearer"},
            raise HttpError(401, "Invalid Credentials")
        return user
