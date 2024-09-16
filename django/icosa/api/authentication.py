from datetime import datetime, timedelta

import jwt
from ninja.errors import HttpError
from ninja.security import HttpBearer

from django.conf import settings
from django.contrib.auth.models import User

ALGORITHM = "HS256"


class AuthBearer(HttpBearer):
    def authenticate(self, request, token):
        print("***************************")
        print("token: ", token)
        authentication_error = HttpError(401, "Invalid Credentialsxxx")
        try:
            payload = jwt.decode(
                token,
                settings.JWT_KEY,
                algorithms=[ALGORITHM],
            )
            print("payload :", payload)
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


def create_access_token(*, data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=timedelta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_KEY,
        algorithm=ALGORITHM,
    )
    return encoded_jwt
