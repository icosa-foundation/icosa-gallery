import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.cache import never_cache
from icosa.forms import (
    NewUserForm,
    PasswordResetConfirmForm,
    PasswordResetForm,
)
from icosa.helpers.email import spawn_send_html_mail
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.user import get_owner
from icosa.models import AssetOwner, DeviceCode
from passlib.context import CryptContext

ALGORITHM = "HS256"

INTERNAL_RESET_SESSION_TOKEN = "_password_reset_token"


def generate_device_code(length=5):
    # Define a string of characters to exclude
    exclude = "I1O0"
    characters = "".join(set(string.ascii_uppercase + string.digits) - set(exclude))
    return "".join(secrets.choice(characters) for i in range(length))


def authenticate_icosa_user(
    username: str,
    password: str,
) -> Optional[AssetOwner]:
    username = username.lower()
    try:
        user = AssetOwner.objects.get(
            email=username
        )  # This code used to check either url or username. Seems odd.

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        if not pwd_context.verify(password, bytes(user.password)):
            return None

        return user

    except AssetOwner.DoesNotExist:
        return None


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
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": f"{user.email}{user.password}"},
        expires_delta=access_token_expires,
    )
    user.access_token = access_token
    user.save()


def custom_login(request):
    if not request.user.is_anonymous:
        return HttpResponseRedirect(reverse("home"))

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
    success = False
    if request.method == "POST":
        form = NewUserForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            url = form.cleaned_data["url"]
            password = form.cleaned_data["password_new"]
            displayname = form.cleaned_data["displayname"]

            salt = bcrypt.gensalt(10)
            hashedpw = bcrypt.hashpw(password.encode(), salt)
            snowflake = generate_snowflake()
            assettoken = secrets.token_urlsafe(8) if url is None else url

            icosa_user = AssetOwner.objects.create(
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
            mail_subject = f"Activate your {current_site.name} account."
            message = render_to_string(
                "auth/confirm_registration_email.html",
                {
                    "request": request,
                    "user": user,
                    "domain": current_site.domain,
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                },
            )
            to_email = form.cleaned_data.get("email")
            spawn_send_html_mail(mail_subject, message, [to_email])
            success = True
    else:
        form = NewUserForm()
    return render(
        request,
        "auth/register.html",
        {
            "form": form,
            "success": success,
        },
    )


def activate_registration(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        success = True
    else:
        success = False
    return render(
        request,
        "auth/activation.html",
        {
            "success": success,
        },
    )


def password_reset(request):
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            try:
                user = User.objects.get(email=form.cleaned_data["email"])

                current_site = get_current_site(request)
                mail_subject = f"Reset your {current_site.name} account password."
                message = render_to_string(
                    "auth/password_reset_email.html",
                    {
                        "request": request,
                        "user": user,
                        "domain": current_site.domain,
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        "token": default_token_generator.make_token(user),
                    },
                )
                to_email = form.cleaned_data.get("email")
                spawn_send_html_mail(mail_subject, message, [to_email])
            except User.DoesNotExist:
                pass
            return redirect(reverse("password_reset_done"))
    else:
        form = PasswordResetForm()
        return render(
            request,
            "auth/password_reset.html",
            {
                "form": form,
            },
        )


def password_reset_done(request):
    return render(
        request,
        "auth/password_reset_done.html",
        {},
    )


def password_reset_confirm(request, uidb64, token):
    valid_link = False
    redirected_url_token = "set-password"
    done = False
    form = PasswordResetConfirmForm()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None:
        if token == redirected_url_token:
            # Store the token in the session and redirect to the password reset
            # form at a URL without the token. That avoids the possibility of
            # leaking the token in the HTTP Referer header.
            session_token = request.session.get(INTERNAL_RESET_SESSION_TOKEN)
            if default_token_generator.check_token(user, session_token):
                valid_link = True
                if request.method == "POST":
                    form = PasswordResetConfirmForm(request.POST)
                    if form.is_valid():
                        password = form.cleaned_data["password_new"]
                        user.set_password(password)
                        user.save()
                        logout(request)
                        icosa_user = get_owner(user)
                        icosa_user.set_password(password)
                        return HttpResponseRedirect(reverse("password_reset_complete"))
        else:
            if default_token_generator.check_token(user, token):
                request.session[INTERNAL_RESET_SESSION_TOKEN] = token
                redirect_url = request.path.replace(token, redirected_url_token)
                return HttpResponseRedirect(redirect_url)

    return render(
        request,
        "auth/password_reset_confirm.html",
        {
            "form": form,
            "valid_link": valid_link,
            "done": done,
            "uidb64": uidb64,
            "token": token,
        },
    )


def password_reset_complete(request):
    return render(
        request,
        "auth/password_reset_complete.html",
        {},
    )


@never_cache
def devicecode(request):
    template = "auth/device.html"
    user = request.user
    context = {}
    if user.is_authenticated:
        owner = AssetOwner.from_django_request(request)
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
