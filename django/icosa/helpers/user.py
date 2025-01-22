import secrets
import string
from datetime import datetime, timedelta

import jwt
from django.conf import settings
from icosa.models import AssetOwner

ALGORITHM = "HS256"


def get_owner(user):
    owner = None
    if not user.is_anonymous:
        try:
            owner = AssetOwner.objects.get(django_user=user)
        except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
            pass
    return owner


def create_access_token(*, data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def save_access_token(user: AssetOwner):
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    subject = f"{user.email}"
    access_token = create_access_token(
        data={"sub": subject},
        expires_delta=expires,
    )
    user.access_token = access_token
    user.save()


def generate_device_code(length=5):
    # Define a string of characters to exclude
    exclude = "I1O0"
    characters = "".join(
        set(string.ascii_uppercase + string.digits) - set(exclude),
    )
    return "".join(secrets.choice(characters) for i in range(length))
