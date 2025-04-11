from datetime import datetime, timedelta, timezone
from django.conf import settings
import jwt

ALGORITHM = "HS256"

class TokenError(Exception):
    pass

class AccessToken:
    """
    A class which validates and wraps an existing JWT or can be used to build a
    new JWT.
    """
    lifetime = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    def __init__(self, token = None, verify = True):
        """
        !!!! IMPORTANT !!!! MUST raise a TokenError with a user-facing error
        message if the given token is invalid, expired, or otherwise not safe
        to use.
        """
        self.token = token
        self.current_time = datetime.now(timezone.utc)

        # Set up token
        if token is not None:
            # An encoded token was provided
            # Decode token
            try:
                self.payload = jwt.decode(
                    token,
                    settings.JWT_KEY,
                    algorithms=[ALGORITHM],
                )
            except jwt.DecodeError as e:
                raise TokenError("Token is invalid") from e
            except jwt.ExpiredSignatureError as e:
                raise TokenError("Token has expired") from e
            except jwt.InvalidTokenError as e:
                raise TokenError("Token is invalid") from e
            except jwt.InvalidSignatureError as e:
                raise TokenError("Token signature is invalid") from e
            except jwt.InvalidAlgorithmError as e:
                raise TokenError("Token algorithm is invalid") from e

        else:
            # New token.  Skip all the verification steps.
            self.payload = {}

            # Set "exp" and "iat" claims with default value
            self.set_exp(from_time=self.current_time, lifetime=self.lifetime)

    def __repr__(self):
        return repr(self.payload)

    def __getitem__(self, key):
        return self.payload[key]

    def __setitem__(self, key, value):
        self.payload[key] = value

    def __delitem__(self, key):
        del self.payload[key]

    def __contains__(self, key):
        return key in self.payload

    def get(self, key, default=None):
        return self.payload.get(key, default)

    def __str__(self):
        """
        Signs and returns a token as a base64 encoded string.
        """
        return jwt.encode(
            self.payload,
            settings.JWT_KEY,
            algorithm=ALGORITHM
        )

    def set_exp(
        self,
        from_time = None,
        lifetime = None,
    ):
        """
        Updates the expiration time of a token.

        See here:
        https://tools.ietf.org/html/rfc7519#section-4.1.4
        """
        if from_time is None:
            from_time = self.current_time

        if lifetime is None:
            lifetime = self.lifetime

        self.payload["exp"] = from_time + lifetime

    @classmethod
    def for_user(cls, user):
        """
        Returns an authorization token for the given user that will be provided
        after authenticating the user's credentials.
        """
        user_email = user.email
        token = cls()
        token["sub"] = user_email

        return token
