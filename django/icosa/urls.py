from icosa.api.assets import router as assets_router
from icosa.api.login import router as login_router
from icosa.api.oembed import router as oembed_router
from icosa.api.poly import router as poly_router
from icosa.api.users import router as users_router
from icosa.jwt.authentication import JWTAuth
from icosa.views import auth as auth_views
from icosa.views import autocomplete as autocomplete_views
from icosa.views import main as main_views
from ninja import NinjaAPI
from ninja.throttling import AnonRateThrottle, AuthRateThrottle

from django.conf import settings
from django.urls import include, path
from django.views.generic import RedirectView

app_name = "icosa"

handler404 = main_views.handler404
handler500 = main_views.handler500

throttle_rules = [
    AnonRateThrottle("60/h"),
    AuthRateThrottle("1000/h"),
]

api_servers = [
    {
        "url": f"{settings.DEPLOYMENT_SCHEME}{settings.API_SERVER}",
        "description": "Development server" if settings.DEBUG else "Production server",
    }
]
if getattr(settings, "STAFF_ONLY_ACCESS", False):
    api = NinjaAPI(
        auth=JWTAuth(),
        throttle=throttle_rules,
        servers=api_servers,
        urls_namespace="icosa:api",
    )
else:
    api = NinjaAPI(
        throttle=throttle_rules,
        servers=api_servers,
        urls_namespace="icosa:api",
    )

api.add_router("assets", assets_router, tags=["Assets"])
api.add_router("login", login_router, tags=["Login"])
api.add_router("oembed", oembed_router, tags=["Oembed"])
api.add_router("poly", poly_router, tags=["Poly"])
api.add_router("users", users_router, tags=["Users"])


urlpatterns = [
    path("div_by_zero", main_views.div_by_zero, name="div_by_zero"),
    path("health", main_views.health, name="health"),
    # Auth views
    path("login", auth_views.custom_login, name="login"),
    path("logout", auth_views.custom_logout, name="logout"),
    path("register", auth_views.register, name="register"),
    path(
        r"activate/<str:uidb64>/<str:token>",
        auth_views.activate_registration,
        name="activate_registration",
    ),
    path("password_reset", auth_views.password_reset, name="password_reset"),
    path(
        "password_reset_done",
        auth_views.password_reset_done,
        name="password_reset_done",
    ),
    path(
        "password_reset_complete",
        auth_views.password_reset_complete,
        name="password_reset_complete",
    ),
    path(
        r"password_reset_confirm/<str:uidb64>/<str:token>",
        auth_views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("device", auth_views.devicecode, name="devicecode"),
    # Other views
    path("", main_views.home, name="home"),
    path(
        "tiltbrush",
        RedirectView.as_view(pattern_name="home_openbrush", permanent=True),
    ),
    path("openbrush", main_views.home_openbrush, name="home_openbrush"),
    path("openblocks", main_views.home_blocks, name="home_blocks"),
    path("other", main_views.home_other, name="home_other"),
    path("explore/<str:category>", main_views.category, name="explore_category"),
    path("uploads", main_views.uploads, name="uploads"),
    path("user/<str:slug>", main_views.user_show, name="user_show"),
    path("owner/<str:slug>", main_views.owner_show, name="owner_show"),
    path("likes", main_views.my_likes, name="my_likes"),
    path(
        "view/<str:asset_url>",
        main_views.asset_view,
        name="asset_view",
    ),
    path(
        "view/<str:asset_url>/embed",
        main_views.asset_oembed,
        name="asset_oembed",
    ),
    path(
        "masthead_image/<str:asset_url>",
        main_views.make_asset_masthead_image,
        name="make_asset_masthead_image",
    ),
    path(
        "thumbnail/<str:asset_url>",
        main_views.make_asset_thumbnail,
        name="make_asset_thumbnail",
    ),
    path(
        "download/<str:asset_url>",
        main_views.asset_downloads,
        name="asset_downloads",
    ),
    path(
        "log_download/<str:asset_url>",
        main_views.asset_log_download,
        name="asset_log_download",
    ),
    path(
        "status/<str:asset_url>",
        main_views.asset_status,
        name="asset_status",
    ),
    path(
        "report/<str:asset_url>",
        main_views.report_asset,
        name="report_asset",
    ),
    path(
        "report-success",
        main_views.report_success,
        name="report_success",
    ),
    path(
        "edit/<str:asset_url>",
        main_views.asset_edit,
        name="asset_edit",
    ),
    path(
        "delete/<str:asset_url>",
        main_views.asset_delete,
        name="asset_delete",
    ),
    path(
        "publish/<str:asset_url>",
        main_views.asset_publish,
        name="asset_publish",
    ),
    path("search", main_views.search, name="search"),
    path("settings", main_views.user_settings, name="settings"),
    path("about", main_views.about, name="about"),
    path("terms", main_views.terms, name="terms"),
    path(
        "information-for-artists-and-creators",
        main_views.artist_info,
        name="artist_info",
    ),
    path("supporters", main_views.supporters, name="supporters"),
    path("licenses", main_views.licenses, name="licenses"),
    path("privacy-policy", main_views.privacy_policy, name="privacy_policy"),
    path("toggle-like", main_views.toggle_like, name="toggle_like"),
    path("waitlist", main_views.waitlist, name="waitlist"),
    # autocomplete views
    path(
        "tag-autocomplete",
        autocomplete_views.TagAutocomplete.as_view(
            create_field="name",
            validate_create=False,
        ),
        name="tag-autocomplete",
    ),
]

if settings.DEPLOYMENT_HOST_API:
    urlpatterns.append(
        path("v1/", api.urls),
    )
else:
    urlpatterns.append(
        path("api/v1/", api.urls),
    )

if getattr(settings, "DEBUG", False):
    urlpatterns += [
        path(
            "debug_password_reset_email",
            auth_views.debug_password_reset_email,
            name="debug_password_reset_email",
        ),
        path(
            "debug_registration_email",
            auth_views.debug_registration_email,
            name="debug_registration_email",
        ),
    ]
