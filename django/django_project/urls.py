from icosa import urls as icosa_urls

from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

handler403 = icosa_urls.handler403
handler404 = icosa_urls.handler404
handler500 = icosa_urls.handler500


urlpatterns = [
    path("", include("icosa.urls")),
    path("admin_tools/", include("admin_tools.urls")),
    path("admin/", admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if (getattr(settings, "DEBUG_TOOLBAR_ENABLED", False)) and "debug_toolbar" in settings.INSTALLED_APPS:
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
    ]
if settings.SILKY_PYTHON_PROFILER:
    urlpatterns += [path("silk", include("silk.urls", namespace="silk"))]
