import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from icosa.forms import NewUserForm
from icosa.helpers.snowflake import generate_snowflake
from icosa.models import DeviceCode
from icosa.models import User as IcosaUser
from passlib.context import CryptContext

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

ALGORITHM = "HS256"


def generate_device_code(length=5):
    # Define a string of characters to exclude
    exclude = "I1O0"
    characters = "".join(
        set(string.ascii_uppercase + string.digits) - set(exclude)
    )
    return "".join(secrets.choice(characters) for i in range(length))


def authenticate_icosa_user(
    username: str,
    password: str,
) -> Optional[IcosaUser]:
    username = username.lower()
    try:
        user = IcosaUser.objects.get(
            email=username
        )  # This code used to check either url or username. Seems odd.

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        if not pwd_context.verify(password, bytes(user.password)):
            return None

        return user

    except IcosaUser.DoesNotExist:
        return None


def create_access_token(*, data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=timedelta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def save_access_token(user: IcosaUser):
    access_token_expires = timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    user.access_token = access_token
    user.save()


def custom_login(request):
    if request.method == "POST":
        username = request.POST.get("username", None)
        password = request.POST.get("password", None)
        # Creating the error response up front is slower for the happy path,
        # but makes the code perhaps more readable.
        error_response = render(
            request,
            "auth/login.html",
            {"error": "Please enter a valid username or password"},
        )

        icosa_user = authenticate_icosa_user(username, password)
        if icosa_user is None:
            # Icosa user auth failed, so we return early.
            print("failed at icosa user")
            return error_response
        else:
            save_access_token(icosa_user)

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"password": password},
        )
        user = authenticate(request, username=username, password=password)
        if user is None:
            # This is really for type safety/data integrity, the django
            # user should pass this test.
            print("failed at django user")
            return error_response
        if created:
            icosa_user.migrated = True
            icosa_user.save()
        else:
            if user.is_active is False:
                # This is the case for when a user has registered, but not
                # yet confirmed their email address. We could provide a more
                # helpful error message here, but that would leak the existence
                # of an incomplete registration.
                print("failed at active user")
                return error_response

        login(request, user)
        return redirect("home")
    else:
        return render(request, "auth/login.html")


def custom_logout(request):
    if request.method == "POST":
        logout(request)
        return redirect("home")
    else:
        return render(request, "auth/logout.html")


def register(request):
    if request.method == "POST":
        form = NewUserForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data["url"]
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password_new"]
            displayname = form.cleaned_data["displayname"]

            salt = bcrypt.gensalt(10)
            hashedpw = bcrypt.hashpw(password.encode(), salt)
            snowflake = generate_snowflake()
            assettoken = secrets.token_urlsafe(8) if url is None else url

            icosa_user = IcosaUser.objects.create(
                id=snowflake,
                url=assettoken,
                email=email,
                password=hashedpw,
                displayname=displayname,
            )

            user = User.objects.create_user(
                username=icosa_user.email,
                email=icosa_user.email,
                password=password,
            )
            user.is_active = False
            user.save()

            current_site = get_current_site(request)
            mail_subject = "Activate your Icosa Gallery account."  # TODO, should probably hook into the site name.
            message = render_to_string(
                "auth/confirm_registration_email.html",
                {
                    "user": user,
                    "domain": current_site.domain,
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": PasswordResetTokenGenerator().make_token(user),
                },
            )
            to_email = form.cleaned_data.get("email")
            email = EmailMessage(
                mail_subject,
                message,
                to=[to_email],
            )
            email.send()
            return HttpResponse(
                "Please confirm your email address to complete the registration"
            )
    else:
        form = NewUserForm()
    return render(request, "auth/register.html", {"form": form})


def activate_registration(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and PasswordResetTokenGenerator().check_token(
        user, token
    ):
        user.is_active = True
        user.save()
        login(request, user)
        # return redirect('home')
        return HttpResponse(
            "Thank you for your email confirmation. Now you can log in."
        )
    else:
        return HttpResponse("Activation link is invalid!")


def devicecode(request):
    template = "auth/device.html"
    user = request.user
    context = {}
    if user.is_authenticated:
        owner = IcosaUser.from_request(request)
        if owner:
            code = generate_device_code()
            expiry_time = datetime.utcnow() + timedelta(minutes=1)

            # Delete all codes for this user
            DeviceCode.objects.filter(user=owner).delete()
            # Delete all expired codes for any user
            DeviceCode.objects.filter(expiry__lt=datetime.utcnow()).delete()

            DeviceCode.objects.create(
                user=owner,
                devicecode=code,
                expiry=expiry_time,
            )

            context = {
                "device_code": code.upper(),
            }
    return render(request, template, context)
