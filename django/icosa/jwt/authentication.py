from django.contrib.auth import get_user_model
from ninja.errors import HttpError
from ninja.security import HttpBearer

from .tokens import AccessToken, TokenError

User = get_user_model()


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
