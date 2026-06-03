from django.contrib import admin

from .models import ScanReport


@admin.register(ScanReport)
class ScanReportAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "hostname", "status", "overall_score", "created_at")
    list_filter = ("status", "owner")
    search_fields = ("hostname", "owner__username", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")
