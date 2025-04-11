import random
import secrets
import time
from typing import Optional

import bcrypt
from constance import config
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
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
from icosa.models import AssetOwner, DeviceCode
from passlib.context import CryptContext

INTERNAL_RESET_SESSION_TOKEN = "_password_reset_token"


def send_password_reset_email(request, user, to_email):
    site = get_current_site(request)
    owner = None
    try:
        owner = AssetOwner.objects.get(django_user=user)
    except AssetOwner.DoesNotExist:
        # TODO(james): We should probably error out here
        pass

    mail_subject = f"Reset your {site.name} account password."
    message = render_to_string(
        "emails/password_reset_email.html",
        {
            "request": request,
            "user": user,
            "owner": owner,
            "domain": site.domain,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    spawn_send_html_mail(mail_subject, message, [to_email])


def send_registration_email(request, user, owner, to_email=None):
    current_site = get_current_site(request)
    mail_subject = f"Activate your {current_site.name} account."
    message = render_to_string(
        "emails/confirm_registration_email.html",
        {
            "request": request,
            "user": user,
            "owner": owner,
            "domain": current_site.domain,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    spawn_send_html_mail(mail_subject, message, [to_email])


def authenticate_icosa_user(
    username: str,
    password: str,
) -> Optional[AssetOwner]:
    username = username.lower()
    try:
        user = AssetOwner.objects.get(email=username)  # This code used to check either url or username. Seems odd.

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        if not pwd_context.verify(password, bytes(user.password)):
            return None

        return user

    except AssetOwner.DoesNotExist:
        return None


@user_passes_test(lambda u: u.is_superuser)
def debug_password_reset_email(request):
    user = request.user
    send_password_reset_email(
        request,
        user,
        settings.ADMIN_EMAIL,
    )
    return HttpResponse("ok")


@user_passes_test(lambda u: u.is_superuser)
def debug_registration_email(request):
    user = request.user
    owner = AssetOwner.objects.get(django_user=user)
    send_registration_email(
        request,
        user,
        owner,
        settings.ADMIN_EMAIL,
    )

    return HttpResponse("ok")


def custom_login(request):
    if not request.user.is_anonymous:
        return HttpResponseRedirect(reverse("home"))

    if request.method == "POST" and config.SIGNUP_OPEN:
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
        # TODO(james): if icosa_user has been merged with another, we probably
        #  don't want to allow them to log in. We need a nice error here that's
        #  not confusing and perhaps different from failing login under normal
        #  circumstances.
        if icosa_user is None:
            # Icosa user auth failed, so we return early.
            return error_response
        else:
            icosa_user.update_access_token()

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
            password = form.cleaned_data["password_new"]
            displayname = form.cleaned_data["displayname"]

            # We want to do the work of accessing the database, creating the
            # password etc in all cases, even if the username is already taken
            # to mitigatie timing attacks.
            salt = bcrypt.gensalt(10)
            hashedpw = bcrypt.hashpw(password.encode(), salt)
            snowflake = generate_snowflake()
            assettoken = secrets.token_urlsafe(8)

            try:
                owner = AssetOwner.objects.create(
                    id=snowflake,
                    url=assettoken,
                    email=email,
                    password=hashedpw,
                    displayname=displayname,
                )
            except IntegrityError:
                pass

            try:
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                )
                user.is_active = False
                user.save()
                owner.django_user = user
                owner.save()
                send_registration_email(request, user, owner, to_email=form.cleaned_data.get("email"))
            except IntegrityError:
                pass
            # Always succeed. The user should never know that an account is
            # already registered.
            success = True
            # Sleep a random amount of time to throw off timing attacks a bit more.
            time.sleep(random.randrange(0, 200) / 100)
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
                send_password_reset_email(
                    request,
                    user,
                    to_email=form.cleaned_data.get("email"),
                )
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
                        icosa_user = AssetOwner.from_django_user(user)
                        icosa_user.set_password(password)
                        return HttpResponseRedirect(
                            reverse("password_reset_complete"),
                        )
        else:
            if default_token_generator.check_token(user, token):
                request.session[INTERNAL_RESET_SESSION_TOKEN] = token
                redirect_url = request.path.replace(
                    token,
                    redirected_url_token,
                )
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
            code = AssetOwner.generate_device_code()
            expiry_time = timezone.now() + timezone.timedelta(minutes=1)

            # Delete all codes for this user
            DeviceCode.objects.filter(user=owner).delete()
            # Delete all expired codes for any user
            DeviceCode.objects.filter(expiry__lt=timezone.now()).delete()

            DeviceCode.objects.create(
                user=owner,
                devicecode=code,
                expiry=expiry_time,
            )

            context = {
                "device_code": code.upper(),
            }
    return render(request, template, context)
