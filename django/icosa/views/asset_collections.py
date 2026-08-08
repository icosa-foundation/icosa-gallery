from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max, Q
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from icosa.forms import AssetCollectionForm
from icosa.helpers.moderation import get_str_content_type
from icosa.model_mixins import MOD_HIDDEN
from icosa.models import (
    PUBLIC,
    UNLISTED,
    Asset,
    AssetCollection,
    AssetCollectionAsset,
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


def _paginate_collections(request, collections):
    paginator = Paginator(collections, settings.PAGINATION_PER_PAGE)
    return paginator, paginator.get_page(request.GET.get("page"))


def _collection_items(collection):
    return collection.collected_assets.select_related("asset").order_by(
        "order",
        "create_time",
        "pk",
    )


def _add_asset_to_collection(collection, asset):
    if collection.collected_assets.filter(asset=asset).exists():
        return
    last_order = collection.collected_assets.aggregate(Max("order"))["order__max"]
    AssetCollectionAsset.objects.create(
        collection=collection,
        asset=asset,
        order=0 if last_order is None else last_order + 1,
    )


def _save_collection_item_order(items):
    changed_items = []
    for order, item in enumerate(items):
        if item.order != order:
            item.order = order
            changed_items.append(item)
    if changed_items:
        AssetCollectionAsset.objects.bulk_update(changed_items, ["order"])


@never_cache
def asset_collection_list(request):
    collections = (
        AssetCollection.objects.filter(visibility=PUBLIC)
        .exclude(moderation_state__in=MOD_HIDDEN)
        .select_related("user")
        .order_by("-update_time")
    )
    paginator, collection_page = _paginate_collections(request, collections)
    return render(
        request,
        "main/asset_collection_list.html",
        {
            "collections": collection_page,
            "assets": collection_page,
            "paginator": paginator,
            "page_title": "Collections",
        },
    )


@login_required
@never_cache
def my_asset_collection_list(request):
    collections = AssetCollection.objects.filter(user=request.user).order_by(
        "-update_time"
    )
    paginator, collection_page = _paginate_collections(request, collections)
    return render(
        request,
        "main/asset_collection_list.html",
        {
            "collections": collection_page,
            "assets": collection_page,
            "paginator": paginator,
            "page_title": "My Collections",
            "show_owner_actions": True,
        },
    )


@login_required
@never_cache
def asset_collection_create(request):
    form = AssetCollectionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        collection = form.save(commit=False)
        collection.user = request.user
        collection.save()
        return redirect("icosa:my_asset_collection_list")
    return render(
        request,
        "main/asset_collection_form.html",
        {
            "form": form,
            "page_title": "Create Collection",
        },
    )


@login_required
@never_cache
def asset_collection_edit(request, collection_url: str):
    collection = get_object_or_404(
        AssetCollection,
        url=collection_url,
        user=request.user,
    )
    form = AssetCollectionForm(
        request.POST or None,
        request.FILES or None,
        instance=collection,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect(collection.get_absolute_url() or "icosa:my_asset_collection_list")
    return render(
        request,
        "main/asset_collection_form.html",
        {
            "collection": collection,
            "collection_items": _collection_items(collection),
            "form": form,
            "page_title": f"Edit {collection.name}",
        },
    )


@login_required
@require_POST
@transaction.atomic
def asset_collection_item_update(request, collection_url: str):
    collection = get_object_or_404(
        AssetCollection,
        url=collection_url,
        user=request.user,
    )
    item = get_object_or_404(
        AssetCollectionAsset,
        pk=request.POST.get("item_id"),
        collection=collection,
    )
    action = request.POST.get("action")
    items = list(_collection_items(collection))
    item_index = next(
        index for index, candidate in enumerate(items) if candidate.pk == item.pk
    )

    if action == "remove":
        items.pop(item_index)
        item.delete()
    elif action == "move_up":
        if item_index > 0:
            items[item_index - 1], items[item_index] = (
                items[item_index],
                items[item_index - 1],
            )
    elif action == "move_down":
        if item_index < len(items) - 1:
            items[item_index], items[item_index + 1] = (
                items[item_index + 1],
                items[item_index],
            )
    else:
        return HttpResponseBadRequest("invalid collection item action")

    _save_collection_item_order(items)
    AssetCollection.objects.filter(pk=collection.pk).update(
        update_time=timezone.now()
    )
    return redirect("icosa:asset_collection_edit", collection_url=collection.url)


@login_required
@require_POST
def asset_collection_delete(request, collection_url: str):
    collection = get_object_or_404(
        AssetCollection,
        url=collection_url,
        user=request.user,
    )
    collection.delete()
    return redirect("icosa:my_asset_collection_list")


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
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        post_data = request.POST
        template = "modals/user_asset_collection_modal_content.html"

        get_object_or_404(
            AssetOwner,
            url=user_url,
            django_user=request.user,
        )
        user = request.user

        try:
            asset = Asset.objects.exclude(moderation_state__in=MOD_HIDDEN).get(
                Q(visibility__in=[PUBLIC, UNLISTED])
                | Q(owner__django_user=request.user),
                url=post_data.get("asset_url"),
            )
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
            _add_asset_to_collection(collection, asset)
        elif action == COLLECTION_REMOVE:
            collection.assets.remove(asset)
        elif action == COLLECTION_NEW:
            name = (post_data.get("new-collection-name") or "").strip()
            if not name:
                return HttpResponseBadRequest("collection name is required")
            collection_data = {
                "user": user,
                "name": name,
            }
            collection = AssetCollection.objects.create(**collection_data)
            _add_asset_to_collection(collection, asset)

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
            django_user__isnull=False,
        )
        user = owner.django_user

        if user == request.user:
            collections = AssetCollection.objects.filter(user=owner.django_user)
        else:
            collections = AssetCollection.objects.filter(
                user=owner.django_user,
                visibility=PUBLIC,
            ).exclude(moderation_state__in=MOD_HIDDEN)
        collections = collections.order_by("-update_time")
        paginator, collection_page = _paginate_collections(request, collections)
        context = {
            "collections": collection_page,
            "assets": collection_page,
            "paginator": paginator,
            "page_title": f"Collections by {user.displayname}",
            "show_owner_actions": user == request.user,
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
        django_user=request.user,
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
        django_user__isnull=False,
    )
    user = owner.django_user
    user_is_moderator = request.user.groups.filter(name="Moderator").exists()

    if user == request.user:
        collection = get_object_or_404(
            AssetCollection,
            url=collection_url,
            user=request.user,
        )
    else:
        collections = AssetCollection.objects.filter(
            visibility__in=[PUBLIC, UNLISTED]
        )
        if not user_is_moderator:
            collections = collections.exclude(moderation_state__in=MOD_HIDDEN)
        collection = get_object_or_404(
            collections,
            url=collection_url,
            user=user,
        )

    asset_objs = collection.collected_assets.filter(asset__visibility=PUBLIC).exclude(
        asset__moderation_state__in=MOD_HIDDEN
    )
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
        "user_is_moderator": user_is_moderator,
        "content_type": get_str_content_type(collection),
    }
    return render(request, template, context)
