from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("stripe/", include("billing.urls")),
    path("", include("diagnostics.urls")),
]
