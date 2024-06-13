from icosa.views import auth as auth_views
from icosa.views import main as main_views

from django.conf.urls import include
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin_tools/", include("admin_tools.urls")),
    path("admin/", admin.site.urls),
    # Auth views
    path("login/", auth_views.custom_login, name="login"),
    path("logout/", auth_views.custom_logout, name="logout"),
    # Other views
    path("", main_views.home, name="home"),
    path("user/<str:user_url>/", main_views.user, name="user"),
    path(
        "view/<str:user_url>/<str:asset_url>/",
        main_views.view_asset,
        name="view_asset",
    ),
    path("settings/", main_views.settings, name="settings"),
    path("terms/", main_views.terms, name="terms"),
]
