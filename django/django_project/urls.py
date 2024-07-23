from icosa.api.assets import router as assets_router
from icosa.api.login import router as login_router
from icosa.api.oembed import router as oembed_router
from icosa.api.poly import router as poly_router
from icosa.api.users import router as users_router
from icosa.views import auth as auth_views
from icosa.views import main as main_views
from ninja import NinjaAPI

from django.conf.urls import include
from django.contrib import admin
from django.urls import path

api = NinjaAPI()
api.add_router("assets", assets_router, tags=["Assets"])
api.add_router("login", login_router, tags=["Login"])
api.add_router("oembed", oembed_router, tags=["Oembed"])
api.add_router("poly", poly_router, tags=["Poly"])
api.add_router("users", users_router, tags=["Users"])

urlpatterns = [
    path("admin_tools/", include("admin_tools.urls")),
    path("admin", admin.site.urls),
    # Auth views
    path("login", auth_views.custom_login, name="login"),
    path("logout", auth_views.custom_logout, name="logout"),
    path("device", auth_views.devicecode, name="devicecode"),
    # Other views
    path("", main_views.home, name="home"),
    path("tiltbrush", main_views.home_tiltbrush, name="home_tiltbrush"),
    path("blocks", main_views.home_blocks, name="home_blocks"),
    path("uploads", main_views.uploads, name="uploads"),
    path("user/<str:user_url>", main_views.user_show, name="user_show"),
    path("likes/", main_views.my_likes, name="my_likes"),
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
        "edit/<str:user_url>/<str:asset_url>",
        main_views.edit_asset,
        name="edit_asset",
    ),
    path("settings/", main_views.user_settings, name="settings"),
    path("terms/", main_views.terms, name="terms"),
    path("api/v1/", api.urls),
]
