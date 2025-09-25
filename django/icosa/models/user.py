import secrets
import string
from datetime import datetime, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    displayname = models.CharField(_("Display Name"), max_length=255)
    email = models.EmailField(_("email address"), blank=True, unique=True)

    def get_absolute_url(self):
        owners = self.assetowner_set.all()
        num_owners = owners.count()
        if num_owners > 1 and owners.first().url:
            url = reverse("icosa:user_show", kwargs={"slug": owners.first().url})
        elif num_owners == 1:
            url = owners.first().get_absolute_url()
        else:
            url = None
        return url

    @staticmethod
    def generate_device_code(length=5):
        # Define a string of characters to exclude
        exclude = "I1O0"
        characters = "".join(
            set(string.ascii_uppercase + string.digits) - set(exclude),
        )
        return "".join(secrets.choice(characters) for i in range(length))

    def generate_access_token(self):
        # TODO don't use JWTs
        ALGORITHM = "HS256"
        to_encode = {"sub": f"{self.email}"}
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_KEY,
            algorithm=ALGORITHM,
        )
        return encoded_jwt

    @property
    def has_single_owner(self):
        return self.assetowner_set.all().count() == 1
