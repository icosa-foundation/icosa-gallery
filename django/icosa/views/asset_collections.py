from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from icosa.models import (
    PUBLIC,
    UNLISTED,
    Asset,
    AssetCollection,
    AssetOwner,
)


def user_asset_collection_list(request, user_url: str):
    if request.method == "POST":
        print(request.POST)
        return JsonResponse({"success": True})
    elif request.method == "GET":
        template = "main/user_asset_collection_list.html"
        owner = get_object_or_404(
            AssetOwner,
            url=user_url,
        )
        user = owner.django_user

        if user == request.user:
            collections = AssetCollection.objects.filter(user=owner.django_user)
        else:
            collections = AssetCollection.objects.filter(user=owner.django_user, visibility__in=[PUBLIC, UNLISTED])
        context = {
            "collections": collections,
            "page_title": f"Collections by {user.displayname}",
            "user": user,
        }
        return render(
            request,
            template,
            context,
        )
    else:
        return HttpResponseNotAllowed(["GET", "POST"])


@login_required
@never_cache
def user_asset_collection_list_modal(request, user_url: str, asset_url: str):
    template = "modals/user_asset_collection_modal_content.html"
    owner = get_object_or_404(
        AssetOwner,
        url=user_url,
    )
    asset = get_object_or_404(
        Asset,
        url=asset_url,
    )
    user = owner.django_user

    if user == request.user:
        collections = AssetCollection.objects.filter(user=owner.django_user)
    else:
        collections = AssetCollection.objects.none()

    # TODO(perf): slow
    for collection in collections:
        has_asset = asset in collection.assets.all()
        collection.has_asset=has_asset

    context = {
        "collections": collections,
        "page_title": f"Collections by {user.displayname}",
        "user": user,
        "asset": asset,
    }
    return render(
        request,
        template,
        context,
    )


def user_asset_collection_view(request, user_url: str, collection_url: str):
    template = "main/asset_collection_view.html"
    owner = get_object_or_404(
        AssetOwner,
        url=user_url,
    )
    user = owner.django_user

    if user == request.user:
        collection = get_object_or_404(AssetCollection, url=collection_url)
    else:
        collection = get_object_or_404(AssetCollection, url=collection_url, visibility__in=[PUBLIC, UNLISTED])

    asset_objs = collection.collected_assets.filter(asset__visibility=PUBLIC)
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "assets": assets,
        "page_number": page_number,
        "result_count": asset_objs.count(),
        "paginator": paginator,
        "page_title": collection.name or "Untitled collection",
        "collection": collection,
        "owner": owner,
    }
    return render(
        request,
        template,
        context,
    )
