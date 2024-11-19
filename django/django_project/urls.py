from icosa.api.assets import router as assets_router
from icosa.api.authentication import AuthBearer
from icosa.api.login import router as login_router
from icosa.api.oembed import router as oembed_router
from icosa.api.poly import router as poly_router
from icosa.api.users import router as users_router
from icosa.views import auth as auth_views
from icosa.views import main as main_views
from ninja import NinjaAPI
from ninja.throttling import AnonRateThrottle, AuthRateThrottle

from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

handler404 = main_views.handler404
handler500 = main_views.handler500

throttle_rules = [
    AnonRateThrottle("60/h"),
    AuthRateThrottle("1000/h"),
]

if getattr(settings, "STAFF_ONLY_ACCESS", False):
    api = NinjaAPI(
        auth=AuthBearer(),
        throttle=[
            AnonRateThrottle("10/h"),
            AuthRateThrottle("100/h"),
        ],
    )
else:
    api = NinjaAPI(
        throttle=[
            AnonRateThrottle("10/h"),
            AuthRateThrottle("100/h"),
        ],
    )

api.add_router("assets", assets_router, tags=["Assets"])
api.add_router("login", login_router, tags=["Login"])
api.add_router("oembed", oembed_router, tags=["Oembed"])
api.add_router("poly", poly_router, tags=["Poly"])
api.add_router("users", users_router, tags=["Users"])

urlpatterns = [
    path("div_by_zero", main_views.div_by_zero, name="div_by_zero"),
    path("admin_tools/", include("admin_tools.urls")),
    path("admin/", admin.site.urls),
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
    path("blocks", main_views.home_blocks, name="home_blocks"),
    path("other", main_views.home_other, name="home_other"),
    path(
        "explore/<str:category>", main_views.category, name="explore_category"
    ),
    path("uploads", main_views.uploads, name="uploads"),
    path("user/<str:user_url>", main_views.user_show, name="user_show"),
    path("likes", main_views.my_likes, name="my_likes"),
    path(
        "view/<str:user_url>/<str:asset_url>",
        main_views.view_asset,
        name="view_asset",
    ),
    path(
        "view/<str:asset_url>",
        main_views.view_poly_asset,
        name="view_poly_asset",
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
        main_views.edit_asset,
        name="edit_asset",
    ),
    path(
        "delete/<str:asset_url>",
        main_views.delete_asset,
        name="delete_asset",
    ),
    path(
        "publish/<str:asset_url>",
        main_views.publish_asset,
        name="publish_asset",
    ),
    path("search", main_views.search, name="search"),
    path("settings", main_views.user_settings, name="settings"),
    path("terms", main_views.terms, name="terms"),
    path(
        "information-for-artists-and-creators",
        main_views.artist_info,
        name="artist_info",
    ),
    path("licenses", main_views.licenses, name="licenses"),
    path("privacy-policy", main_views.privacy_policy, name="privacy_policy"),
    path("toggle-like", main_views.toggle_like, name="toggle_like"),
]

if settings.DEPLOYMENT_HOST_API:
    urlpatterns.append(
        path("v1/", api.urls),
    )
else:
    urlpatterns.append(
        path("api/v1/", api.urls),
    )
if (
    getattr(settings, "DEBUG_TOOLBAR_ENABLED", False)
) and "debug_toolbar" in settings.INSTALLED_APPS:
    urlpatterns = [
        path("__debug__/", include("debug_toolbar.urls")),
    ] + urlpatterns
