from icosa.forms import AssetSettingsForm, UserSettingsForm
from icosa.helpers.user import get_owner
from icosa.models import PUBLIC, Asset, User

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse


def home(request):
    template = "main/home.html"

    context = {
        "assets": Asset.objects.filter(visibility=PUBLIC).order_by("-id"),
        "hero": Asset.objects.filter(visibility=PUBLIC, curated=True)
        .order_by("?")
        .first(),
    }
    return render(
        request,
        template,
        context,
    )


@login_required
def uploads(request):
    template = "main/asset_list.html"

    user = User.from_request(request)
    context = {
        "assets": Asset.objects.filter(owner=user).order_by("-id"),
    }
    return render(
        request,
        template,
        context,
    )


def user(request, user_url):
    template = "main/user.html"

    user = get_object_or_404(User, url=user_url)
    context = {
        "user": user,
        "assets": Asset.objects.filter(
            visibility=PUBLIC, owner=user.id
        ).order_by("-id"),
    }
    return render(
        request,
        template,
        context,
    )


def view_asset(request, user_url, asset_url):
    template = "main/view_asset.html"
    user = get_object_or_404(User, url=user_url)
    context = {
        "user": user,
        "asset": get_object_or_404(
            Asset, visibility=PUBLIC, owner=user.id, url=asset_url
        ),
    }
    return render(
        request,
        template,
        context,
    )


def edit_asset(request, user_url, asset_url):
    template = "main/edit_asset.html"
    user = get_object_or_404(User, url=user_url)
    asset = get_object_or_404(Asset, owner=user.id, url=asset_url)
    if request.method == "GET":
        form = AssetSettingsForm(instance=asset)
    elif request.method == "POST":
        form = AssetSettingsForm(request.POST, instance=asset)
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
