from api.models import PUBLIC, Asset, User

from django.shortcuts import get_object_or_404, render


def home(request):
    template = "home.html"

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
    template = "user.html"

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
