from django.contrib import admin

from .models import DriverSource, ScanReport


@admin.register(ScanReport)
class ScanReportAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "hostname", "status", "overall_score", "created_at")
    list_filter = ("status", "owner")
    search_fields = ("hostname", "owner__username", "owner__email")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(DriverSource)
class DriverSourceAdmin(admin.ModelAdmin):
    list_display = (
        "vendor_name",
        "customer_segment",
        "source_type",
        "priority",
        "is_active",
    )
    list_filter = ("customer_segment", "source_type", "is_active")
    search_fields = ("vendor_name", "match_terms", "key", "customer_segment")
    ordering = ("customer_segment", "priority", "vendor_name")
