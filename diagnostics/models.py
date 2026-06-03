import uuid

from django.conf import settings
from django.db import models


class ScanReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SCANNING = "scanning", "Scanning"
        ANALYZING = "analyzing", "Analyzing"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scan_reports",
    )
    hostname = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    scan_progress = models.PositiveSmallIntegerField(default=0)
    scan_stage = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    system_snapshot = models.JSONField(default=dict, blank=True)
    ai_analysis = models.JSONField(default=dict, blank=True)
    overall_score = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scan {self.hostname or self.id} ({self.status})"


class DriverSource(models.Model):
    class SourceType(models.TextChoices):
        OEM = "oem", "OEM"
        COMPONENT = "component", "Component"
        GENERIC = "generic", "Generic"

    key = models.SlugField(max_length=64, unique=True)
    vendor_name = models.CharField(max_length=120)
    match_terms = models.TextField(
        help_text="Comma-separated terms used for matching (e.g. dell,latitude,optiplex)",
        blank=True,
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.GENERIC,
    )
    support_url = models.URLField(blank=True)
    driver_url = models.URLField(blank=True)
    troubleshooting_url = models.URLField(blank=True)
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "vendor_name"]

    def __str__(self):
        return f"{self.vendor_name} ({self.source_type})"
