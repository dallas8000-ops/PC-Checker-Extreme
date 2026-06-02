from django.urls import path

from . import views

app_name = "diagnostics"

urlpatterns = [
    path("", views.home, name="home"),
    path("scan/start/", views.start_scan, name="start_scan"),
    path("scan/<uuid:report_id>/progress/", views.scan_progress, name="scan_progress"),
    path("api/scan/<uuid:report_id>/status/", views.scan_status, name="scan_status"),
    path("scan/<uuid:report_id>/", views.report_detail, name="report_detail"),
    path("scan/<uuid:report_id>/export/html/", views.export_html, name="export_html"),
    path("scan/<uuid:report_id>/export/pdf/", views.export_pdf, name="export_pdf"),
    path("compare/", views.compare_scans, name="compare_scans"),
    path("api/scan/<uuid:report_id>/", views.report_json, name="report_json"),
    path("api/health/", views.api_health, name="api_health"),
]
