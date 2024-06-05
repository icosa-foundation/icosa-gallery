from api.forms import UserSettingsForm
from api.models import PUBLIC, Asset, User
from api.utils import get_owner

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render


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


def user(request, slug):
    template = "main/user.html"

    user = get_object_or_404(User, url=slug)
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
