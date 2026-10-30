from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "diagnostics"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("app/", views.home, name="home"),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", views.signup, name="signup"),
    path("scan/start/", views.start_scan, name="start_scan"),
    path("scan/<uuid:report_id>/progress/", views.scan_progress, name="scan_progress"),
    path("api/scan/<uuid:report_id>/status/", views.scan_status, name="scan_status"),
    path("scan/<uuid:report_id>/", views.report_detail, name="report_detail"),
    path("api/fix/", views.apply_fix, name="apply_fix"),
    path("tools/", views.device_tools_page, name="device_tools"),
    path("api/tools/run/", views.run_device_tool, name="run_device_tool"),
    path("scan/<uuid:report_id>/export/html/", views.export_html, name="export_html"),
    path("scan/<uuid:report_id>/export/pdf/", views.export_pdf, name="export_pdf"),
    path("compare/", views.compare_scans, name="compare_scans"),
    path("scan/<uuid:report_id>/chat/", views.scan_chat, name="scan_chat"),
    path("api/scan/<uuid:report_id>/", views.report_json, name="report_json"),
    path("api/driver-lookup/", views.driver_lookup, name="driver_lookup"),
    path("api/health/", views.api_health, name="api_health"),
]
