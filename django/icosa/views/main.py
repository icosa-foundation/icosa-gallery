from icosa.forms import AssetSettingsForm, AssetUploadForm, UserSettingsForm
from icosa.helpers.file import upload_asset
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.user import get_owner
from icosa.models import PRIVATE, PUBLIC, UNLISTED, Asset
from icosa.models import User as IcosaUser

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
    asset_objs = (
        Asset.objects.filter(inc_q).exclude(exc_q).distinct().order_by("-id")
    )
    paginator = Paginator(asset_objs, 40)
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
        Q(visibility=PUBLIC, polyresource__format__format_type="TILT"),
        show_hero=True,
    )


def home_blocks(request):
    return landing_page(
        request,
        Q(
            visibility=PUBLIC,
            polyresource__format__format_type__in=[
                "GLTF",
                "GLTF2",
            ],
        ),
        Q(polyresource__format__format_type="TILT"),
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
    context = {
        "assets": Asset.objects.filter(owner=user).order_by("-id"),
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

    context = {
        "user": owner,
        "assets": Asset.objects.filter(q).order_by("-id"),
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
    liked_assets = owner.likes.filter(q)

    context = {
        "user": owner,
        "assets": liked_assets,
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
        print(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse("uploads"))
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    context = {
        "user": user,
        "asset": asset,
        "form": form,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
def settings(request):
    template = "main/settings.html"
    user = request.user
    owner = get_owner(user)
    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=owner, user=user)
        if form.is_valid():
            updated_owner = form.save()
            password_new = request.POST.get("password_new")
            need_login = False
            if password_new:
                user.set_password(password_new)
                need_login = True
            email = request.POST.get("email")
            if email and owner.email != updated_owner.email:
                user.email = email
                need_login = True
            user.save()
            if need_login:
                return redirect("login")

    else:
        form = UserSettingsForm(instance=owner, user=user)
    context = {"form": form}
    return render(request, template, context)


def terms(request):
    template = "main/terms.html"

    return render(
        request,
        template,
    )
