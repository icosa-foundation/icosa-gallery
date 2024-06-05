from api.views import main as main_views

from django.conf.urls import include
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin_tools/", include("admin_tools.urls")),
    path("admin/", admin.site.urls),
    path("", main_views.home, name="home"),
    path("user/<str:slug>/", main_views.user, name="user"),
]
