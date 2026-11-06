from django.urls import re_path
from django.contrib import admin
from django.urls import include, path

from core.views import media

urlpatterns = [
    re_path(r"^media/(?P<name>.+)$", media, name="media"),
    path("api/v1/", include("core.api.urls")),  # results API for the field app + Situation Room
    path("admin/", admin.site.urls),  # reserved for administrators
    path("", include("core.urls")),
]
