import inspect
import random
import secrets

from constance import config
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sites.shortcuts import get_current_site
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from honeypot.decorators import check_honeypot
from icosa.forms import (
    ARTIST_QUERY_SUBJECT_CHOICES,
    ArtistQueryForm,
    AssetEditForm,
    AssetPublishForm,
    AssetReportForm,
    AssetUploadForm,
    UserSettingsForm,
)
from icosa.helpers.email import spawn_send_html_mail
from icosa.helpers.file import b64_to_img
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.upload_web_ui import upload
from icosa.models import (
    ALL_RIGHTS_RESERVED,
    ARCHIVED,
    ASSET_STATE_BARE,
    ASSET_STATE_FAILED,
    ASSET_STATE_UPLOADING,
    CATEGORY_LABEL_MAP,
    CATEGORY_LABELS,
    PRIVATE,
    PUBLIC,
    UNLISTED,
    Asset,
    AssetOwner,
    MastheadSection,
    UserLike,
)
from icosa.tasks import queue_upload_asset_web_ui
from silk.profiling.profiler import silk_profile

User = get_user_model()

POLY_USER_URL = "4aEd8rQgKu2"

# TODO(james): not sure how to decide on a decent rank. As of writing, our
# top-ranked asset is at 80459.
MASTHEAD_TOP_RANK = 10000
MASTHEAD_CACHE_SECONDS = 10
MASTHEAD_CACHE_PREFIX = "mastheads"


def set_viewer_js_version(request):
    viewer_js_version = request.GET.get("viewerjs", None)
    if viewer_js_version is not None:
        viewer_js_version = viewer_js_version.lower()
        if viewer_js_version in ["experimental", "previous"]:
            request.session["viewer_js_version"] = viewer_js_version
        else:
            if request.session.get("viewer_js_version", None) is not None:
                del request.session["viewer_js_version"]


def get_default_q():
    try:
        if config.HIDE_REPORTED_ASSETS:
            return Q(
                visibility=PUBLIC,
                is_viewer_compatible=True,
                curated=True,
                last_reported_time__isnull=True,
            )
        return Q(
            visibility=PUBLIC,
            is_viewer_compatible=True,
            curated=True,
        )
    except Exception:
        return Q(
            visibility=PUBLIC,
            is_viewer_compatible=True,
            curated=True,
            last_reported_time__isnull=True,
        )


def user_can_view_asset(
    user: AbstractBaseUser,
    asset: Asset,
) -> bool:
    # Superusers should be able to view any asset. Preferably while showing a
    # banner and with the option to check the real access.
    if user.is_staff or user.is_superuser:
        return True
    if asset.visibility in [PRIVATE, ARCHIVED]:
        return user.is_authenticated and asset.owner.django_user == user
    return True


def check_user_can_view_asset(
    user: AbstractBaseUser,
    asset: Asset,
):
    if not user_can_view_asset(user, asset):
        raise Http404()


def handler404(request, exception):
    return render(request, "main/404.html", status=404)


def handler500(request):
    return render(request, "main/500.html", status=500)


def handler403(request, exception=None):
    if isinstance(exception, Ratelimited):
        return render(request, "main/429.html", status=429)
    return HttpResponseForbidden("Forbidden")


@user_passes_test(lambda u: u.is_superuser)
@never_cache
def div_by_zero(request):
    1 / 0


@never_cache
def health(request):
    return HttpResponse("ok")


def landing_page(
    request,
    assets=Asset.objects.filter(get_default_q()).select_related("owner"),
    show_masthead=True,
    heading=None,
    heading_link=None,
    is_explore_heading=False,
):
    # Inspects this landing page function's caller's name so we don't have
    # to worry about passing in unique values for each landing page's cache
    # key. Neglecting to use - or repeating another - cache key has the subtle
    # effect of showing unrelated mastheads.
    curframe = inspect.currentframe()
    calframe = inspect.getouterframes(curframe, 2)
    landing_page_fn_name = calframe[1][3]

    template = "main/home.html"

    # TODO(james): filter out assets with no formats
    assets = (
        assets.exclude(license__isnull=True)
        .exclude(license=ALL_RIGHTS_RESERVED)
        .select_related("owner")
        .prefetch_related("resource_set", "format_set")
    )

    try:
        page_number = int(request.GET.get("page", 1))
    except ValueError:
        page_number = 0

    # Only show the masthead if we're on page 1 of a lister.
    # If show_masthead is false, keep it that way.
    if show_masthead is True and (page_number is None or page_number < 2):
        # The mastheads query is slow, but we still want a rotating list on
        # every page load. Cache a list of mastheads and choose one at random
        # each time.
        cache_key = f"{MASTHEAD_CACHE_PREFIX}-{landing_page_fn_name}"
        if cache.get(cache_key):
            mastheads = cache.get(cache_key)
        else:
            mastheads = list(MastheadSection.objects.all())

            cache.set(
                f"{MASTHEAD_CACHE_PREFIX}-{landing_page_fn_name}",
                mastheads,
                MASTHEAD_CACHE_SECONDS,
            )
    else:
        mastheads = []
    masthead = random.choice(mastheads) if mastheads else None

    # Our cached masthead might have been made private since caching it.
    # This query is still quicker than filtering all possible mastheads
    # by visibility and should only result in a missing masthead on rare
    # occasions.
    if masthead is not None and not masthead.visibility == PUBLIC:
        masthead = None

    paginator = Paginator(assets.order_by("-rank"), settings.PAGINATION_PER_PAGE)
    assets = paginator.get_page(page_number)
    page_title = f"Exploring {heading}" if is_explore_heading else heading
    context = {
        "assets": assets,
        "masthead": masthead,
        "heading": heading,
        "heading_link": heading_link,
        "is_explore_heading": is_explore_heading,
        "page_title": page_title,
        "paginator": paginator,
    }
    return render(
        request,
        template,
        context,
    )


@silk_profile(name="Home page")
@never_cache
def home(request):
    return landing_page(request)


@never_cache
def home_openbrush(request):
    assets = Asset.objects.filter(
        visibility=PUBLIC,
        has_tilt=True,
        curated=True,
    )

    return landing_page(
        request,
        assets,
        heading="Open Brush",
        heading_link="https://openbrush.app",
        is_explore_heading=True,
        show_masthead=False,
    )


@never_cache
def home_blocks(request):
    poly_by_google_q = Q(visibility=PUBLIC, owner__url=POLY_USER_URL)
    blocks_q = Q(visibility=PUBLIC, has_blocks=True, curated=True)
    q = poly_by_google_q | blocks_q

    assets = Asset.objects.filter(q)

    return landing_page(
        request,
        assets,
        heading="Open Blocks",
        heading_link="https://openblocks.app",
        is_explore_heading=True,
        show_masthead=True,
    )


@user_passes_test(lambda u: u.is_superuser)
@never_cache
def home_other(request):
    if config.HIDE_REPORTED_ASSETS:
        home_q = Q(
            is_viewer_compatible=True,
            curated=True,
            last_reported_time__isnull=True,
        )
    else:
        home_q = Q(
            is_viewer_compatible=True,
            curated=True,
        )
    poly_by_google_q = Q(owner__url=POLY_USER_URL)
    only_blocks_q = Q(has_blocks=True, curated=True)
    blocks_q = poly_by_google_q | only_blocks_q
    tilt_q = Q(
        has_tilt=True,
        curated=True,
    )
    exclude_q = home_q | blocks_q | tilt_q
    assets = Asset.objects.filter(visibility=PUBLIC).exclude(exclude_q)

    return landing_page(
        request,
        assets,
        show_masthead=True,
        heading="""stuff not on /blocks or /openbrush""",
    )


@never_cache
def category(request, category):
    category_label = category.upper()
    if category_label not in CATEGORY_LABELS:
        raise Http404()
    assets = Asset.objects.filter(
        visibility=PUBLIC,
        category=category_label,
        curated=True,
    )
    category_name = CATEGORY_LABEL_MAP.get(category)
    return landing_page(
        request,
        assets,
        show_masthead=False,
        heading=f"Exploring: {category_name}",
    )


@login_required
@never_cache
def uploads(request):
    template = "main/manage_uploads.html"

    user = request.user
    if request.method == "POST":
        form = AssetUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job_snowflake = generate_snowflake()
            asset_token = secrets.token_urlsafe(8)
            with transaction.atomic():
                owner, _ = AssetOwner.objects.get_or_create(
                    django_user=user,
                    email=user.email,
                    defaults={
                        "url": secrets.token_urlsafe(8),
                        "displayname": user.displayname,
                    },
                )
                asset = Asset.objects.create(
                    id=job_snowflake,
                    url=asset_token,
                    owner=owner,
                    state=ASSET_STATE_UPLOADING,
                )
                try:
                    if getattr(settings, "ENABLE_TASK_QUEUE", True) is True:
                        queue_upload_asset_web_ui(
                            current_user=user,
                            asset=asset,
                            files=[request.FILES["file"]],
                        )
                    else:
                        upload(
                            asset,
                            [request.FILES["file"]],
                        )
                except Exception:
                    asset.state = ASSET_STATE_FAILED
                    asset.save()

            messages.add_message(request, messages.INFO, "Your upload has started.")
            return HttpResponseRedirect(reverse("icosa:uploads"))
    elif request.method == "GET":
        form = AssetUploadForm()
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    asset_objs = Asset.objects.filter(owner__django_user=user).exclude(state=ASSET_STATE_BARE).order_by("-create_time")
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)

    context = {
        "assets": assets,
        "form": form,
        "page_title": "My Uploads",
        "paginator": paginator,
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def owner_show(request, slug):
    template = "main/user_show.html"
    owner = get_object_or_404(
        AssetOwner,
        url=slug,
    )

    if owner.disable_profile and not request.user.is_superuser:
        raise Http404

    asset_objs = owner.asset_set.filter(
        visibility=PUBLIC,
    ).order_by("-id")

    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "user": request.user,
        "owner": owner,
        "assets": assets,
        "page_title": owner.displayname,
        "paginator": paginator,
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def user_show(request, slug):
    template = "main/user_show.html"

    # A django User is always accessible via one of their AssetOwner instances
    # and never directly.

    # If a django User has no AssetOwner instances, we have no content to show
    # anyway, so there is no need to provide a direct link.

    # This view shows all assets for all Asset Owner instances associated with
    # a django User.

    owner = get_object_or_404(
        AssetOwner,
        url=slug,
    )

    if owner.disable_profile and not request.user.is_superuser:
        raise Http404

    if owner.django_user is None:
        owners = AssetOwner.objects.filter(pk=owner.pk)
    else:
        owners = owner.django_user.assetowner_set.all()

    asset_objs = Asset.objects.filter(
        owner__in=owners,
        visibility=PUBLIC,
    ).order_by("-id")

    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)

    if owners.count() > 1:
        if owner.django_user:
            page_title = f"{owner.django_user.displayname} and others"
        else:
            page_title = owner.displayname
    else:
        page_title = owner.get_displayname()

    context = {
        "owner": owner,
        "assets": assets,
        "page_title": page_title,
        "paginator": paginator,
        "is_multi_owner": bool(owners.count()),
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
@login_required
def my_likes(request):
    template = "main/likes.html"

    user = request.user
    q = Q(asset__visibility__in=[PUBLIC, UNLISTED])
    q |= Q(asset__visibility__in=[PRIVATE, UNLISTED], asset__owner__django_user=user)

    liked_assets = UserLike.objects.filter(user=user).filter(q)
    asset_objs = [ul.asset for ul in liked_assets]
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)

    context = {
        "user": user,
        "assets": assets,
        "page_title": "My likes",
        "paginator": paginator,
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def asset_view(request, asset_url):
    template = "main/asset_view.html"
    user = request.user

    asset = get_object_or_404(Asset.objects.prefetch_related("resource_set", "format_set"), url=asset_url)
    check_user_can_view_asset(user, asset)
    asset.inc_views_and_rank()
    format_override = request.GET.get("forceformat", "")

    set_viewer_js_version(request)

    embed_code = render_to_string(
        "partials/oembed_code.html",
        {
            "host": f"{settings.DEPLOYMENT_SCHEME}{settings.DEPLOYMENT_HOST_WEB}",
            "asset": asset,
            "frame_width": 1920,
            "frame_height": 1440,
        },
    )

    if user.is_anonymous:
        user_owns_asset = False
    else:
        user_owns_asset = asset.owner in user.assetowner_set.all()
    context = {
        "user_owns_asset": user_owns_asset,
        "asset": asset,
        "format_override": format_override,
        "downloadable_formats": bool(asset.get_all_downloadable_formats(user)),
        "page_title": asset.name,
        "embed_code": embed_code.strip(),
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
@user_passes_test(lambda u: u.is_superuser)
def asset_forward_to_admin_change(request, asset_url):
    # NOTE(safety) This view exists solely so as to not expose asset IDs on the
    # front end. At time of writing, only superusers can see this, but I don't
    # want putting links with IDs on the front end to become a practice.

    asset = get_object_or_404(Asset, url=asset_url)

    return HttpResponseRedirect(
        reverse(
            "admin:icosa_asset_change",
            kwargs={"object_id": asset.id},
        )
    )


@xframe_options_exempt
@never_cache
def asset_oembed(request, asset_url):
    template = "main/asset_embed.html"

    user = request.user
    asset = get_object_or_404(Asset, url=asset_url)
    check_user_can_view_asset(user, asset)
    asset.inc_views_and_rank()  # TODO: do we count embedded views separately or at all?
    format_override = request.GET.get("forceformat", "")

    set_viewer_js_version(request)

    context = {
        "asset": asset,
        "format_override": format_override,
        "downloadable_formats": bool(asset.get_all_downloadable_formats(user)),
        "page_title": f"embed {asset.name}",
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def asset_downloads(request, asset_url):
    asset = get_object_or_404(Asset, url=asset_url)
    if asset.license == ALL_RIGHTS_RESERVED:
        raise Http404()
    user = request.user

    template = "main/asset_downloads.html"
    check_user_can_view_asset(user, asset)

    context = {
        "asset": asset,
        "downloadable_formats": asset.get_all_downloadable_formats(user),
        "page_title": f"Download {asset.name}",
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def asset_log_download(request, asset_url):
    if request.method == "POST":
        asset = get_object_or_404(Asset, url=asset_url)
        asset.downloads += 1
        asset.save()

        return HttpResponse("ok")
    else:
        return HttpResponseNotAllowed(["POST"])


@login_required
@never_cache
def asset_status(request, asset_url):
    template = "partials/asset_status.html"
    asset = get_object_or_404(Asset, url=asset_url, owner__in=request.user.assetowner_set.all())
    context = {
        "asset": asset,
        "is_polling": True,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
@never_cache
def asset_edit(request, asset_url):
    template = "main/asset_edit.html"
    is_superuser = request.user.is_superuser
    if is_superuser:
        asset = get_object_or_404(Asset, url=asset_url)
    else:
        asset = get_object_or_404(Asset, url=asset_url, owner__in=request.user.assetowner_set.all())
    # We need to disconnect the editable state from the form during validation.
    # Without this, if the form contains errors, some fields that need
    # correction cannot be edited.
    is_editable = asset.model_is_editable

    if request.method == "GET":
        form = AssetEditForm(instance=asset)
    elif request.method == "POST":
        form = AssetEditForm(request.POST, request.FILES, instance=asset)
        if form.is_valid():
            with transaction.atomic():
                asset = form.save(commit=False)
                override_thumbnail = request.POST.get("thumbnail_override", False)
                thumbnail_override_image = request.POST.get("thumbnail_override_image", None)
                if override_thumbnail and thumbnail_override_image:
                    image_file = b64_to_img(thumbnail_override_image)
                    asset.thumbnail = image_file
                form.save_m2m()
                if is_editable and "_save_private" in request.POST:
                    asset.visibility = PRIVATE
                if "_save_public" in request.POST:
                    asset.visibility = PUBLIC
                if "_save_unlisted" in request.POST:
                    asset.visibility = UNLISTED
                asset.save(update_timestamps=True)

                if request.FILES.get("zip_file"):
                    asset.state = ASSET_STATE_UPLOADING
                    asset.save(update_timestamps=True)

                    if getattr(settings, "ENABLE_TASK_QUEUE", True) is True:
                        queue_upload_asset_web_ui(
                            current_user=request.user,
                            asset=asset,
                            files=[request.FILES["zip_file"]],
                        )
                    else:
                        upload(
                            asset,
                            [request.FILES["zip_file"]],
                        )
            if is_superuser:
                return HttpResponseRedirect(reverse("icosa:asset_view", kwargs={"asset_url": asset.url}))
            else:
                return HttpResponseRedirect(reverse("icosa:uploads"))
        else:
            if settings.DEBUG:
                print(form.errors)
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    set_viewer_js_version(request)

    context = {
        "asset": asset,
        "is_editable": is_editable,
        "form": form,
        "page_title": f"Edit {asset.name}",
    }
    return render(
        request,
        template,
        context,
    )


@login_required
@never_cache
def asset_publish(request, asset_url):
    # TODO(james): This view is very similar to asset_edit
    template = "main/asset_edit.html"
    asset = get_object_or_404(Asset, url=asset_url)
    # We need to disconnect the editable state from the form during validation.
    # Without this, if the form contains errors, some fields that need
    # correction cannot be edited.
    is_editable = asset.model_is_editable

    if request.user != asset.owner.django_user:
        raise Http404()

    if request.method == "GET":
        form = AssetPublishForm(instance=asset)
    elif request.method == "POST":
        form = AssetPublishForm(request.POST, request.FILES, instance=asset)
        if form.is_valid():
            with transaction.atomic():
                asset = form.save()
                if is_editable and "_save_private" in request.POST:
                    asset.visibility = PRIVATE
                if "_save_public" in request.POST:
                    asset.visibility = PUBLIC
                if "_save_unlisted" in request.POST:
                    asset.visibility = UNLISTED
                asset.save(update_timestamps=True)
            return HttpResponseRedirect(reverse("icosa:uploads"))
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    context = {
        "is_editable": asset.model_is_editable,
        "asset": asset,
        "form": form,
        "page_title": f"Publish {asset.name}",
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
@login_required
def asset_delete(request, asset_url):
    if request.method == "POST":
        with transaction.atomic():
            asset = get_object_or_404(Asset, url=asset_url, owner__in=request.user.assetowner_set.all())
            if asset.name:
                asset_name = asset.name
            else:
                asset_name = "Unnamed asset"

            asset.hide_media()
            asset.delete()
        messages.add_message(
            request,
            messages.INFO,
            f"Deleted '{asset_name}'.",
        )
        return HttpResponseRedirect(reverse("icosa:uploads"))
    else:
        return HttpResponseNotAllowed(["POST"])


@ratelimit(key="user_or_ip", rate="5/m", method="POST")
@check_honeypot
@never_cache
def report_asset(request, asset_url):
    template = "main/report_asset.html"
    asset = get_object_or_404(Asset, url=asset_url)
    if request.method == "GET":
        form = AssetReportForm(initial={"asset_url": asset.url})
    elif request.method == "POST":
        form = AssetReportForm(request.POST)
        if form.is_valid():
            asset.last_reported_time = timezone.now()
            reporter = request.user if not request.user.is_anonymous else None
            if reporter is None:
                reporter_email = None
            else:
                reporter_email = reporter.email
                asset.last_reported_by = reporter
            asset.save()
            current_site = get_current_site(request)
            mail_subject = "An Icosa asset has been reported"
            to_email = getattr(settings, "ADMIN_EMAIL", None)
            if to_email is not None:
                message = render_to_string(
                    "emails/report_asset_email.html",
                    {
                        "asset": asset,
                        "request": request,
                        "reporter": reporter_email,
                        "reason": form.cleaned_data["reason_for_reporting"],
                        "domain": current_site.domain,
                    },
                )
                spawn_send_html_mail(mail_subject, message, [to_email])
            return HttpResponseRedirect(reverse("icosa:report_success"))
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    context = {
        "asset": asset,
        "form": form,
        "page_title": f"Report {asset.name}",
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def report_success(request):
    return template_view(
        request,
        "main/report_success.html",
        "Reported work successfully",
    )


@never_cache
@login_required
def user_settings(request):
    need_login = False
    template = "main/settings.html"
    user = request.user
    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=user)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                password_new = request.POST.get("password_new")
                if password_new:
                    user.set_password(password_new)
                    need_login = True
                email = request.POST.get("email")
                if email:
                    user.email = email
                user.save()

                if user.has_single_owner:
                    description = form.cleaned_data.get("description", None)
                    url = form.cleaned_data.get("url", None)
                    if settings.DEBUG:
                        print(description, url)
                    owner = user.assetowner_set.first()
                    if description is not None:
                        owner.description = description
                    if url is not None:
                        owner.url = url
                    owner.save()

            if need_login:
                logout(request)

    else:
        form = UserSettingsForm(instance=user)
    context = {
        "form": form,
        "need_login": need_login,
        "page_title": f"{user.username} User settings",
    }
    return render(request, template, context)


def template_view(request, template, page_title=None):
    context = {"page_title": page_title}
    return render(
        request,
        template,
        context,
    )


def terms(request):
    return template_view(
        request,
        "main/terms.html",
        "Website usage terms and conditions",
    )


def supporters(request):
    return template_view(
        request,
        "main/supporters.html",
        "Our supporters",
    )


def artist_info(request):
    template = "main/info_for_artists.html"
    subject = ""
    if request.method == "GET":
        form = ArtistQueryForm()
    elif request.method == "POST":
        # Assuming that the form is posted via htmx, so we are returning
        # a partial.
        form = ArtistQueryForm(request.POST)
        subject = dict(form.fields["subject"].choices).get(request.POST.get("subject"))
        if form.is_valid():
            current_site = get_current_site(request)
            mail_subject = f"Enquiry from {current_site.name}: {subject}"
            contact_email = form.cleaned_data.get("contact_email")
            message = form.cleaned_data.get("message")
            message = render_to_string(
                "emails/artist_enquiry_email.html",
                {
                    "contact_email": contact_email,
                    "message": message,
                },
            )
            spawn_send_html_mail(mail_subject, message, [settings.ADMIN_EMAIL])
            template = "partials/enquiry_modal_content_success.html"
        else:
            # get_subject_display() only works for modelforms, unbelievably.
            template = "partials/enquiry_modal_content.html"
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    context = {
        "form": form,
        "subject_choices": ARTIST_QUERY_SUBJECT_CHOICES,
        "subject": subject,
        "page_title": "Information for Artists and Creators",
    }
    return render(request, template, context)


def licenses(request):
    return template_view(
        request,
        "main/licenses.html",
        "What types of licenses are available?",
    )


def privacy_policy(request):
    return template_view(
        request,
        "main/privacy_policy.html",
        "Privacy Policy",
    )


def about(request):
    return template_view(
        request,
        "main/about.html",
        "About Icosa Gallery",
    )


@never_cache
def search(request):
    query = request.GET.get("s")
    template = "main/search.html"

    if config.HIDE_REPORTED_ASSETS:
        q = Q(
            visibility=PUBLIC,
            is_viewer_compatible=True,
            last_reported_time__isnull=True,
        )
    else:
        q = Q(
            visibility=PUBLIC,
            is_viewer_compatible=True,
        )

    if query is not None:
        q &= Q(search_text__icontains=query)

    asset_objs = (
        Asset.objects.filter(q).exclude(license__isnull=True).exclude(license=ALL_RIGHTS_RESERVED).order_by("-rank")
    )
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "assets": assets,
        "page_number": page_number,
        "result_count": asset_objs.count(),
        "search_query": query,
        "page_title": f"Search for {query}",
        "paginator": paginator,
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
def toggle_like(request):
    error_return = HttpResponse(status=422)

    user = request.user
    if user is None or user.is_anonymous:
        return error_return

    asset_url = request.POST.get("assetId", None)
    if asset_url is None:
        return error_return

    try:
        asset = Asset.objects.get(url=asset_url)
    except Asset.DoesNotExist:
        return error_return

    is_liked = asset.id in UserLike.objects.filter(user=user).values_list("asset__id", flat=True)
    with transaction.atomic():
        if is_liked:
            UserLike.objects.filter(user=user, asset=asset).delete()
        else:
            UserLike.objects.create(user=user, asset=asset)
        # Triggers denorming of asset liked time, but not update_time.
        asset.save()
    template = "main/tags/like_button.html"
    context = {
        "is_liked": not is_liked,
        "asset_url": asset.url,
    }
    return render(
        request,
        template,
        context,
    )


@never_cache
@user_passes_test(lambda u: u.is_superuser)
def make_asset_thumbnail(request, asset_url):
    if request.method == "POST":
        asset = get_object_or_404(Asset, url=asset_url)
        b64_image = request.POST.get("thumbnail_image", None)
        if not b64_image:
            return HttpResponseBadRequest("No image data received")

        image_file = b64_to_img(b64_image)

        asset.preview_image = image_file
        asset.save()
        body = f"<p>Image saved</p><p><a href='{asset.get_absolute_url()}'>Back to asset</a></p><p><a href='/'>Back to home</a></p>"

        return HttpResponse(mark_safe(body))
    else:
        return HttpResponseNotAllowed(["POST"])


@never_cache
@user_passes_test(lambda u: u.is_superuser)
def make_asset_masthead_image(request, asset_url):
    if request.method == "POST":
        asset = get_object_or_404(Asset, url=asset_url)
        b64_image = request.POST.get("masthead_image", None)
        if not b64_image:
            return HttpResponseBadRequest("No image data received")

        image_file = b64_to_img(b64_image)
        create = {
            "asset": asset,
        }
        with transaction.atomic():
            masthead = MastheadSection.objects.create(**create)
            # We need an instance ID to populate the image path in storage.
            # So we need to save it separately after the create.
            masthead.image = image_file
            masthead.save()
        body = f"<p>Image saved</p><p><a href='{asset.get_absolute_url()}'>Back to asset</a></p><p><a href='/'>Back to home</a></p>"

        return HttpResponse(mark_safe(body))
    else:
        return HttpResponseNotAllowed(["POST"])


@never_cache
def waitlist(request):
    template = "main/waitlist.html"
    if not config.WAITLIST_IF_SIGNUP_CLOSED and not config.SIGNUP_OPEN:
        raise Http404()

    context = {
        "page_title": "Join the waitlist",
    }

    return render(
        request,
        template,
        context,
    )
