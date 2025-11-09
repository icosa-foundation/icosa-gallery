from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from icosa.forms import CollectionEditForm
from icosa.models import (
    PUBLIC,
    UNLISTED,
    Asset,
    AssetCollection,
    AssetOwner,
)

COLLECTION_ADD = "ADD"
COLLECTION_REMOVE = "REMOVE"
COLLECTION_NEW = "NEW"

COLLECTION_ACTIONS = {
    "_add_to_collection": COLLECTION_ADD,
    "_remove_from_collection": COLLECTION_REMOVE,
    "_add_to_new_collection": COLLECTION_NEW,
}


def get_user_collections(request, user, asset):
    if user == request.user:
        collections = AssetCollection.objects.filter(user=user)
    else:
        collections = AssetCollection.objects.none()

    # TODO(perf): slow
    for collection in collections:
        has_asset = asset in collection.assets.all()
        collection.has_asset = has_asset

    return collections


def user_asset_collection_list(request, user_url: str):
    if request.method == "POST":
        post_data = request.POST
        template = "modals/user_asset_collection_modal_content.html"

        try:
            owner = AssetOwner.objects.get(url=user_url)
        except (AssetOwner.DoesNotExist, AssetOwner.MultipleObjectsReturned):
            return HttpResponseBadRequest
        user = owner.django_user

        try:
            asset = Asset.objects.get(url=post_data.get("asset_url"))
        except (Asset.DoesNotExist, Asset.MultipleObjectsReturned):
            return HttpResponseBadRequest("no valid asset")

        action = None
        collection_url = None
        for key in post_data.keys():
            try:
                action, collection_url = key.split("__")
                action = COLLECTION_ACTIONS.get(action)
                break
            except ValueError:
                pass
            if key == "_add_to_new_collection":
                action = COLLECTION_ACTIONS.get(key)
                break

        if action is None:
            return HttpResponseBadRequest("no action")
        if action in [COLLECTION_ADD, COLLECTION_REMOVE] and collection_url is None:
            return HttpResponseBadRequest(f"action: {action}, collection: {collection_url}")
        if action in [COLLECTION_ADD, COLLECTION_REMOVE]:
            try:
                collection = AssetCollection.objects.get(url=collection_url, user=request.user)
            except (AssetCollection.DoesNotExist, AssetCollection.MultipleObjectsReturned):
                return HttpResponseBadRequest("no collection")

        if action == COLLECTION_ADD:
            collection.assets.add(asset)
        elif action == COLLECTION_REMOVE:
            collection.assets.remove(asset)
        elif action == COLLECTION_NEW:
            name = post_data.get("new-collection-name")
            if name is None:
                return HttpResponseBadRequest("name is none")
            collection_data = {
                "user": user,
                "name": name,
            }
            collection = AssetCollection.objects.create(**collection_data)
            collection.assets.add(asset)

        collections = get_user_collections(request, user, asset)

        context = {
            "collections": collections,
            "page_title": f"Collections by {user.displayname}",
            "user": user,
            "asset": asset,
        }
        return render(request, template, context)
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
        return render(request, template, context)
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
        collections = AssetCollection.objects.filter(user=user)
    else:
        collections = AssetCollection.objects.none()

    # TODO(perf): slow
    for collection in collections:
        has_asset = asset in collection.assets.all()
        collection.has_asset = has_asset

    context = {
        "collections": collections,
        "page_title": f"Collections by {user.displayname}",
        "user": user,
        "asset": asset,
    }
    return render(request, template, context)


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
    return render(request, template, context)


@login_required
@never_cache
def my_collections(request):
    template = "main/manage_collections.html"

    if request.method == "POST":
        form = CollectionEditForm(request.POST, request.FILES)
        if form.is_valid():
            collection = form.save(commit=False)
            collection.user = request.user
            collection.save()
            messages.success(request, "Collection created successfully!")
            return redirect("icosa:my_collections")
    else:
        form = CollectionEditForm()

    collections = AssetCollection.objects.filter(user=request.user).order_by("-create_time")
    paginator = Paginator(collections, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    collections_page = paginator.get_page(page_number)

    context = {
        "collections": collections_page,
        "page_title": "My Collections",
        "form": form,
        "paginator": paginator,
    }
    return render(request, template, context)


@login_required
@never_cache
def collection_edit(request, collection_url: str):
    template = "main/collection_edit.html"
    collection = get_object_or_404(AssetCollection, url=collection_url)

    if collection.user != request.user:
        return HttpResponseForbidden()

    if request.method == "POST":
        form = CollectionEditForm(request.POST, request.FILES, instance=collection)
        if form.is_valid():
            form.save()
            messages.success(request, "Collection updated successfully!")
            return redirect("icosa:collection_edit", collection_url=collection.url)
    else:
        form = CollectionEditForm(instance=collection)

    context = {
        "collection": collection,
        "form": form,
        "page_title": f"Edit {collection.name}",
    }
    return render(request, template, context)


@login_required
@never_cache
def collection_delete(request, collection_url: str):
    collection = get_object_or_404(AssetCollection, url=collection_url)

    if collection.user != request.user:
        return HttpResponseForbidden()

    if request.method == "POST":
        collection.delete()
        messages.success(request, "Collection deleted successfully!")
        return redirect("icosa:my_collections")

    template = "main/collection_delete.html"
    context = {
        "collection": collection,
        "page_title": f"Delete {collection.name}",
    }
    return render(request, template, context)
