import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest
from ninja.errors import HttpError
from ninja.security import HttpBearer
from ninja.security.http import HttpAuthBase

from .tokens import AccessToken, TokenError

logger = logging.getLogger("django")

User = get_user_model()


class CustomHttpAuthBase(HttpAuthBase, ABC):
    openapi_scheme: str = "bearer"
    header: str = "Authorization"

    def __call__(self, request: HttpRequest) -> Optional[Any]:
        headers = request.headers
        auth_value = headers.get(self.header)
        if not auth_value:
            return AnonymousUser()  # if there is no key, we return AnonymousUser object
        parts = auth_value.split(" ")

        if parts[0].lower() != self.openapi_scheme:
            if settings.DEBUG:
                logger.error(f"Unexpected auth - '{auth_value}'")
            return None
        token = " ".join(parts[1:])
        return self.authenticate(request, token)

    @abstractmethod
    def authenticate(self, request: HttpRequest, token: str) -> Optional[Any]:
        pass  # pragma: no cover


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        authentication_error = HttpError(401, "Invalid Credentials")
        try:
            token = AccessToken(token)
            email = token.get("sub")
            if email is None:
                # headers={"WWW-Authenticate": "Bearer"},
                raise authentication_error
        except TokenError:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        try:
            user = User.objects.get(email=email)
        except User.MultipleObjectsReturned:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        if user is None:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        if not user.is_active:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        request.user = user
        return user


class MaybeJWTAuth(CustomHttpAuthBase):
    def authenticate(self, request, token):
        if token is None:
            return AnonymousUser
        authentication_error = HttpError(401, "Invalid Credentials")
        try:
            token = AccessToken(token)
            email = token.get("sub")
            if email is None:
                # headers={"WWW-Authenticate": "Bearer"},
                raise authentication_error
        except TokenError:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        try:
            user = User.objects.get(email=email)
        except User.MultipleObjectsReturned:
            # headers={"WWW-Authenticate": "Bearer"},
            # TODO: or do we want to return the first that we find?
            raise authentication_error
        if user is None:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        if not user.is_active:
            # headers={"WWW-Authenticate": "Bearer"},
            raise authentication_error
        request.user = user
        return user
