from django.contrib import admin

from .models import ScanReport


@admin.register(ScanReport)
class ScanReportAdmin(admin.ModelAdmin):
    list_display = ("id", "hostname", "status", "overall_score", "created_at")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at")
