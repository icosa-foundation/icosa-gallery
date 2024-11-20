import secrets

from honeypot.decorators import check_honeypot
from icosa.forms import (
    ARTIST_QUERY_SUBJECT_CHOICES,
    ArtistQueryForm,
    AssetReportForm,
    AssetSettingsForm,
    AssetUploadForm,
    UserSettingsForm,
)
from icosa.helpers.email import spawn_send_html_mail
from icosa.helpers.file import upload_asset
from icosa.helpers.snowflake import generate_snowflake
from icosa.helpers.user import get_owner
from icosa.models import (
    ALL_RIGHTS_RESERVED,
    ASSET_STATE_BARE,
    ASSET_STATE_UPLOADING,
    CATEGORY_LABELS,
    PRIVATE,
    PUBLIC,
    UNLISTED,
    Asset,
)
from icosa.models import User as IcosaUser
from icosa.tasks import queue_upload_asset

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User as DjangoUser
from django.contrib.sites.shortcuts import get_current_site
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

POLY_USER_URL = "4aEd8rQgKu2"


def user_can_view_asset(
    user: DjangoUser,
    asset: Asset,
) -> bool:
    if asset.visibility == PRIVATE:
        return (
            user.is_authenticated
            and IcosaUser.from_django_user(user) == asset.owner
        )
    return True


def check_user_can_view_asset(
    user: DjangoUser,
    asset: Asset,
):
    if not user_can_view_asset(user, asset):
        raise Http404()


def handler404(request, exception):
    return render(request, "main/404.html", status=404)


def handler500(request):
    return render(request, "main/500.html", status=500)


@user_passes_test(lambda u: u.is_superuser)
@never_cache
def div_by_zero(request):
    1 / 0


def landing_page(
    request,
    assets=Asset.objects.filter(
        visibility=PUBLIC,
        is_viewer_compatible=True,
        curated=True,
        last_reported_time__isnull=True,
    ),
    show_hero=True,
    heading=None,
):
    template = "main/home.html"
    assets = (
        assets.exclude(license__isnull=True)
        .exclude(license=ALL_RIGHTS_RESERVED)
        .select_related("owner")
    )
    if show_hero is True:
        hero = (
            assets.filter(
                curated=True,
            )
            .order_by("-rank")
            .first()
        )
    else:
        hero = None
    # TODO(james): filter out assets with no formats
    paginator = Paginator(
        assets.order_by("-rank"), settings.PAGINATION_PER_PAGE
    )
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "assets": assets,
        "hero": hero,
        "page_number": page_number,
        "heading": heading,
    }
    return render(
        request,
        template,
        context,
    )


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
        heading="Exploring OpenBrush",
        show_hero=False,
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
        show_hero=True,
        heading="Exploring Blocks",
    )


@user_passes_test(lambda u: u.is_superuser)
@never_cache
def home_other(request):
    home_q = Q(
        is_viewer_compatible=True,
        curated=True,
        last_reported_time__isnull=True,
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
        show_hero=True,
        heading="""stuff not on /blocks or /openbrush""",
    )


def category(request, category):
    category_label = category.upper()
    if category_label not in CATEGORY_LABELS:
        raise Http404()
    assets = Asset.objects.filter(
        visibility=PUBLIC,
        category=category_label,
        curated=True,
    )
    category_name = settings.ASSET_CATEGORY_LABEL_MAP.get(category)
    return landing_page(
        request,
        assets,
        show_hero=False,
        heading=f"Exploring: {category_name}",
    )


@login_required
@never_cache
def uploads(request):
    template = "main/manage_uploads.html"

    user = IcosaUser.from_django_request(request)
    if request.method == "POST":
        form = AssetUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job_snowflake = generate_snowflake()
            asset_token = secrets.token_urlsafe(8)
            asset = Asset.objects.create(
                id=job_snowflake,
                url=asset_token,
                owner=user,
                state=ASSET_STATE_UPLOADING,
            )
            if getattr(settings, "ENABLE_TASK_QUEUE", True) is True:
                queue_upload_asset(
                    current_user=user,
                    asset=asset,
                    files=[request.FILES["file"]],
                )
            else:
                upload_asset(
                    user,
                    asset,
                    [request.FILES["file"]],
                )
            messages.add_message(
                request, messages.INFO, "Your upload has started."
            )
            return HttpResponseRedirect(reverse("uploads"))
    elif request.method == "GET":
        form = AssetUploadForm()
    else:
        return HttpResponseNotAllowed(["GET", "POST"])

    asset_objs = (
        Asset.objects.filter(owner=user)
        .exclude(state=ASSET_STATE_BARE)
        .order_by("-create_time")
    )
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
    if IcosaUser.from_django_request(request) != owner:
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

    owner = IcosaUser.from_django_request(request)
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


# TODO(james): This is very similar to view_poly_asset. Do we need both?
@never_cache
def view_asset(request, user_url, asset_url):
    template = "main/view_asset.html"
    icosa_user = get_object_or_404(IcosaUser, url=user_url)
    asset = get_object_or_404(Asset, owner=icosa_user.id, url=asset_url)
    check_user_can_view_asset(request.user, asset)
    asset.inc_views_and_rank()
    context = {
        "request_user": IcosaUser.from_django_user(request.user),
        "user": icosa_user,
        "asset": asset,
        "asset_files": asset.get_all_absolute_file_names(),
    }
    return render(
        request,
        template,
        context,
    )


# TODO(james): This is very similar to view_asset. Do we need both?
@never_cache
def view_poly_asset(request, asset_url):
    template = "main/view_asset.html"

    asset = get_object_or_404(Asset, url=asset_url)
    check_user_can_view_asset(request.user, asset)
    asset.inc_views_and_rank()
    override_suffix = request.GET.get("nosuffix", "")
    format_override = request.GET.get("forceformat", "")

    context = {
        "request_user": IcosaUser.from_django_user(request.user),
        "user": asset.owner,
        "asset": asset,
        "asset_files": asset.get_all_absolute_file_names(),
        "override_suffix": override_suffix,
        "format_override": format_override,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
@never_cache
def asset_status(request, asset_url):
    template = "partials/asset_status.html"
    owner = IcosaUser.from_django_user(request.user)
    asset = get_object_or_404(Asset, url=asset_url, owner=owner)
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
def edit_asset(request, asset_url):
    template = "main/edit_asset.html"
    owner = IcosaUser.from_django_user(request.user)
    asset = get_object_or_404(Asset, owner=owner, url=asset_url)
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
        "asset": asset,
        "form": form,
    }
    return render(
        request,
        template,
        context,
    )


@login_required
def delete_asset(request, asset_url):
    if request.method == "POST":
        owner = IcosaUser.from_django_user(request.user)
        asset = get_object_or_404(Asset, owner=owner, url=asset_url)
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
        return HttpResponseRedirect(reverse("uploads"))
    else:
        return HttpResponseNotAllowed(["POST"])


@login_required
def publish_asset(request, asset_url):
    template = "main/edit_asset.html"
    asset = get_object_or_404(Asset, url=asset_url)
    if IcosaUser.from_django_user(request.user) != asset.owner:
        raise Http404()
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
        "user": asset.owner,
        "asset": asset,
        "form": form,
    }
    return render(
        request,
        template,
        context,
    )


@check_honeypot
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
                reporter = IcosaUser.from_django_user(reporter)
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
                        "request": request,
                        "reporter": reporter_email,
                        "reason": form.cleaned_data["reason_for_reporting"],
                        "domain": current_site.domain,
                    },
                )
                spawn_send_html_mail(mail_subject, message, [to_email])
            return HttpResponseRedirect(reverse("report_success"))
    else:
        return HttpResponseNotAllowed(["GET", "POST"])
    context = {
        "asset": asset,
        "form": form,
    }
    return render(
        request,
        template,
        context,
    )


def report_success(request):
    return template_view(request, "main/report_success.html")


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


def template_view(request, template):
    return render(
        request,
        template,
    )


def terms(request):
    return template_view(request, "main/terms.html")


def artist_info(request):
    template = "main/info_for_artists.html"
    subject = ""
    if request.method == "GET":
        form = ArtistQueryForm()
    elif request.method == "POST":
        # Assuming that the form is posted via htmx, so we are returning
        # a partial.
        form = ArtistQueryForm(request.POST)
        subject = dict(form.fields["subject"].choices).get(
            request.POST.get("subject")
        )
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
    }
    return render(request, template, context)


def licenses(request):
    return template_view(request, "main/licenses.html")


def privacy_policy(request):
    return template_view(request, "main/privacy_policy.html")


def search(request):
    query = request.GET.get("s")
    template = "main/search.html"

    q = Q(
        visibility=PUBLIC,
        is_viewer_compatible=True,
        last_reported_time__isnull=True,
    )

    if query is not None:
        q &= Q(search_text__icontains=query)

    asset_objs = (
        Asset.objects.filter(q)
        .exclude(license__isnull=True)
        .exclude(license=ALL_RIGHTS_RESERVED)
        .order_by("-id")
    )
    paginator = Paginator(asset_objs, settings.PAGINATION_PER_PAGE)
    page_number = request.GET.get("page")
    assets = paginator.get_page(page_number)
    context = {
        "assets": assets,
        "page_number": page_number,
        "result_count": asset_objs.count(),
        "search_query": query,
    }
    return render(
        request,
        template,
        context,
    )


def toggle_like(request):
    error_return = HttpResponse(status=422)

    owner = IcosaUser.from_django_request(request)
    if owner is None:
        return error_return

    asset_url = request.POST.get("assetId", None)
    if asset_url is None:
        return error_return

    try:
        asset = Asset.objects.get(url=asset_url)
    except Asset.DoesNotExist:
        return error_return

    is_liked = asset.id in owner.likes.values_list("id", flat=True)
    if is_liked:
        owner.likes.remove(asset)
    else:
        owner.likes.add(asset)
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
