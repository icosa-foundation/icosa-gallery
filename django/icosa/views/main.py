from icosa.forms import AssetSettingsForm, AssetUploadForm, UserSettingsForm
from icosa.helpers.file import upload_asset
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.user import get_owner
from icosa.models import PRIVATE, PUBLIC, UNLISTED, Asset
from icosa.models import User as IcosaUser

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse


def landing_page(
    request,
    inc_q=Q(visibility=PUBLIC),
    exc_q=Q(),
    show_hero=True,
):
    template = "main/home.html"
    if show_hero is True:
        hero = (
            Asset.objects.filter(
                curated=True,
            )
            .filter(inc_q)
            .exclude(exc_q)
            .distinct()
            .order_by("?")
            .first()
        )
    else:
        hero = None
    # TODO(james): filter out assets with no formats
    asset_objs = (
        Asset.objects.filter(inc_q).exclude(exc_q).distinct().order_by("-id")
    )
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "assets": assets,
        "hero": hero,
        "page_number": page_number,
    }
    return render(
        request,
        template,
        context,
    )


def home(request):
    return landing_page(request)


def home_tiltbrush(request):
    return landing_page(
        request,
        Q(
            visibility=PUBLIC,
            polyresource__format__format_type="TILT",
        ),
        show_hero=True,
    )


def home_blocks(request):
    return landing_page(
        request,
        Q(
            visibility=PUBLIC,
            polyresource__format__format_type="BLOCKS",
        ),
        show_hero=True,
    )


@login_required
def uploads(request):
    template = "main/manage_uploads.html"

    user = IcosaUser.from_request(request)
    if request.method == "POST":
        form = AssetUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job_snowflake = generate_snowflake()
            upload_asset(
                user,
                job_snowflake,
                [request.FILES["file"]],
                None,
            )
            return HttpResponseRedirect(reverse("uploads"))
    elif request.method == "GET":
        form = AssetUploadForm()
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    asset_objs = Asset.objects.filter(owner=user)
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)

    context = {
        "assets": assets,
        "form": form,
    }
    return render(
        request,
        template,
        context,
    )


def user_show(request, user_url):
    template = "main/user_show.html"

    owner = get_object_or_404(IcosaUser, url=user_url)
    q = Q(owner=owner.id)
    if IcosaUser.from_request(request) != owner:
        q &= Q(visibility=PUBLIC)

    asset_objs = Asset.objects.filter(q).order_by("-id")
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "user": owner,
        "assets": assets,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
def my_likes(request):
    template = "main/likes.html"

    owner = IcosaUser.from_request(request)
    q = Q(visibility__in=[PUBLIC, UNLISTED])
    q |= Q(visibility__in=[PRIVATE, UNLISTED], owner=owner)

    asset_objs = owner.likes.filter(q)
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)

    context = {
        "user": owner,
        "assets": assets,
    }
    return render(
        request,
        template,
        context,
    )


def get_gltf_mode(request, asset):
    if request.GET.get("gltfmode", None) is not None:
        try:
            gltf_mode = int(request.GET["gltfmode"])
        except ValueError:
            pass
    else:
        gltf_mode = None
    return gltf_mode


def view_asset(request, user_url, asset_url):
    template = "main/view_asset.html"
    user = get_object_or_404(IcosaUser, url=user_url)
    asset = get_object_or_404(
        Asset, visibility=PUBLIC, owner=user.id, url=asset_url
    )
    context = {
        "user": user,
        "asset": asset,
        "gltf_mode": get_gltf_mode(request, asset),
    }
    return render(
        request,
        template,
        context,
    )


def view_poly_asset(request, asset_url):
    template = "main/view_asset.html"

    asset = get_object_or_404(Asset, visibility=PUBLIC, url=asset_url)
    context = {
        "user": asset.owner,
        "asset": asset,
        "gltf_mode": get_gltf_mode(request, asset),
    }
    return render(
        request,
        template,
        context,
    )


@login_required
def edit_asset(request, user_url, asset_url):
    template = "main/edit_asset.html"
    user = get_object_or_404(IcosaUser, url=user_url)
    asset = get_object_or_404(Asset, owner=user.id, url=asset_url)
    if request.method == "GET":
        form = AssetSettingsForm(instance=asset)
    elif request.method == "POST":
        form = AssetSettingsForm(request.POST, request.FILES, instance=asset)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("uploads"))
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    context = {
        "user": user,
        "asset": asset,
        "gltf_mode": get_gltf_mode(request, asset),
        "form": form,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
def user_settings(request):
    need_login = False
    template = "main/settings.html"
    user = request.user
    icosa_user = get_owner(user)
    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=icosa_user, user=user)
        if form.is_valid():
            updated_user = form.save()
            password_new = request.POST.get("password_new")
            if password_new:
                user.set_password(password_new)
                icosa_user.set_password(password_new)
                need_login = True
            email = request.POST.get("email")
            if email and icosa_user.email != updated_user.email:
                user.email = email
                need_login = True
            user.save()
            if need_login:
                logout(request)

    else:
        form = UserSettingsForm(instance=icosa_user, user=user)
    context = {
        "form": form,
        "need_login": need_login,
    }
    return render(request, template, context)


def terms(request):
    template = "main/terms.html"

    return render(
        request,
        template,
    )
