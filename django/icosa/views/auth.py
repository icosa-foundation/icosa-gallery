import random
import time
from typing import Optional

from constance import config
from django.conf import settings
from django.contrib.auth import (
    REDIRECT_FIELD_NAME,
    authenticate,
    get_user_model,
    login,
    logout,
)
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.db import IntegrityError, transaction
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit
from honeypot.decorators import check_honeypot
from icosa.forms import (
    NewUserForm,
    PasswordResetConfirmForm,
    PasswordResetForm,
)
from icosa.helpers.email import spawn_send_html_mail
from icosa.models import AssetOwner, DeviceCode

INTERNAL_RESET_SESSION_TOKEN = "_password_reset_token"

User = get_user_model()


def dummy_key(group, request):
    # Return the same key every time. This essentially bypasses the key
    # entirely and rate limits the route regardless of who is accessing it.
    return "number9"


def send_password_reset_email(request, user, to_email):
    site = get_current_site(request)

    mail_subject = f"Reset your {site.name} account password."
    message = render_to_string(
        "emails/password_reset_email.html",
        {
            "request": request,
            "user": user,
            "domain": site.domain,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    spawn_send_html_mail(mail_subject, message, [to_email])


def send_registration_email(request, user, to_email=None):
    current_site = get_current_site(request)
    mail_subject = f"Activate your {current_site.name} account."
    message = render_to_string(
        "emails/confirm_registration_email.html",
        {
            "request": request,
            "user": user,
            "domain": current_site.domain,
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )
    spawn_send_html_mail(mail_subject, message, [to_email])


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


def render_login_error(request, error: Optional[str] = None):
    return render(
        request,
        "auth/login.html",
        {"error": error},
    )


def custom_login(request):
    redirect_to = request.GET.get(REDIRECT_FIELD_NAME, None)

    if not request.user.is_anonymous:
        if redirect_to is not None:
            return HttpResponseRedirect(redirect_to)
        return redirect("icosa:home")

    if not config.LOGIN_OPEN:
        raise Http404()

    if request.method == "POST":
        username = request.POST.get("username", None)
        password = request.POST.get("password", None)
        # Creating the error response up front is slower for the happy path,
        # but makes the code perhaps more readable.
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            # Icosa user auth failed, so we return early.
            return render_login_error(request, "Please enter a valid username or password")

        login(request, user)

        # Claim any assets that were created before the user logged in
        # TODO: Improve and make it configurable (dedicated view, rules for claiming, etc.)

        with transaction.atomic():
            asset_owners = AssetOwner.objects.get_unclaimed_for_user(user)

            for owner in asset_owners:
                owner.django_user = user
                owner.is_claimed = True
                owner.save()

        if redirect_to is not None:
            return HttpResponseRedirect(redirect_to)
        return redirect("icosa:home")
    else:
        return render(
            request,
            "auth/login.html",
            {
                "redirect_to": redirect_to,
                "redirect_to_field_name": REDIRECT_FIELD_NAME,
            },
        )


def custom_logout(request):
    if request.method == "POST":
        logout(request)
        return redirect("icosa:home")
    else:
        return render(request, "auth/logout.html")


@ratelimit(key="ip", rate="10/m", method="POST")
@ratelimit(key="ip", rate="40/d", method="POST")
@ratelimit(key="icosa.views.auth.dummy_key", rate="200/d", method="POST")
@check_honeypot()
@never_cache
def register(request):
    if not config.SIGNUP_OPEN:
        raise Http404()

    success = False
    if request.method == "POST":
        form = NewUserForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password_new"]
            username = form.cleaned_data["username"]
            displayname = form.cleaned_data["displayname"]
            if not User.objects.filter(email=email).exists():
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            username=username,
                            displayname=displayname,
                            email=email,
                            password=password,
                        )
                        user.is_active = False
                        user.save()

                    send_registration_email(request, user, to_email=form.cleaned_data.get("email"))
                except IntegrityError:
                    pass
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


@never_cache
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


@never_cache
@ratelimit(key="user_or_ip", rate="5/m", method="POST")
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
            return redirect(reverse("icosa:password_reset_done"))
    else:
        form = PasswordResetForm()
        return render(
            request,
            "auth/password_reset.html",
            {
                "form": form,
            },
        )


@never_cache
def password_reset_done(request):
    return render(
        request,
        "auth/password_reset_done.html",
        {},
    )


@never_cache
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
                        return HttpResponseRedirect(
                            reverse("icosa:password_reset_complete"),
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


@never_cache
def password_reset_complete(request):
    return render(
        request,
        "auth/password_reset_complete.html",
        {},
    )


@never_cache
def devicecode(request):
    # This function generates device codes for authenticated users which are
    # exchanged for application keys at api/v1/device_login.
    #
    # If the querystring is populated, we instead present a form which posts to
    # the user's local machine with the querystring and device code. The local
    # server should accept these data and post to api/v1/device_login.
    #
    # This is a workaround for having a terrible keyboard experience on some
    # headsets running Open Brush.
    template = "auth/device.html"
    user = request.user
    context = {}
    if user.is_authenticated:
        if request.method == "GET":
            query_dict = {k.lower(): v for k, v in request.GET.items()}
            client_secret = None
            client_id = None
            form_action = None

            if len(request.GET.keys()) == 1:
                # Deprecated form where the one query param key is the client
                # secret. Comes from Open Brush
                client_secret = list(request.GET.keys())[0]
                # Check that the secret query param is an empty key. If it has
                # a value, the request is malformed.
                if client_secret and not request.GET.get(client_secret):
                    client_id = "Open Brush"
                    form_action = "http://localhost:40074/device_login/v1"
            elif len(request.GET.keys()) == 2:
                client_secret = query_dict.get("secret", None)
                client_id = query_dict.get("appid", None)

            if client_id == "openblocks":
                client_id = "Open Blocks"
                form_action = "http://localhost:40084/api/v1/device_login"
            if client_id == "openbrush":
                client_id = "Open Brush"
                form_action = "http://localhost:40074/device_login/v1"

            code = User.generate_device_code()
            expiry_time = timezone.now() + timezone.timedelta(minutes=1)

            with transaction.atomic():
                # Delete all codes for this user
                DeviceCode.objects.filter(user=user).delete()
                # Delete all expired codes for any user
                DeviceCode.objects.filter(expiry__lt=timezone.now()).delete()

                DeviceCode.objects.create(
                    user=user,
                    devicecode=code,
                    expiry=expiry_time,
                )

        context = {
            "device_code": code.upper(),
            "client_secret": client_secret,
            "client_id": client_id,
            "form_action": form_action,
        }
    return render(request, template, context)
