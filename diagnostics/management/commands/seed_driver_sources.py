from django.core.management.base import BaseCommand

from diagnostics.models import DriverSource
from diagnostics.services.driver_lookup import DEFAULT_SOURCES

SEGMENT_CHOICES = {
    "general",
    "smallbiz",
    "msp",
    "enterprise",
    "gaming",
    "creative",
}

# Lower number = higher priority within a segment.
SEGMENT_PRIORITY_OVERRIDES = {
    "general": {
        "dell": 10,
        "hp": 20,
        "lenovo": 30,
        "asus": 40,
        "acer": 50,
        "msi": 60,
        "intel": 70,
        "amd": 80,
        "nvidia": 90,
        "realtek": 100,
    },
    "smallbiz": {
        "hp": 10,
        "dell": 20,
        "lenovo": 30,
        "intel": 40,
        "realtek": 50,
        "nvidia": 60,
        "amd": 70,
        "asus": 80,
        "acer": 90,
        "msi": 100,
    },
    "msp": {
        "dell": 10,
        "lenovo": 20,
        "hp": 30,
        "intel": 40,
        "realtek": 50,
        "nvidia": 60,
        "amd": 70,
        "asus": 80,
        "acer": 90,
        "msi": 100,
    },
    "enterprise": {
        "lenovo": 10,
        "dell": 20,
        "hp": 30,
        "intel": 40,
        "realtek": 50,
        "nvidia": 60,
        "amd": 70,
        "asus": 80,
        "acer": 90,
        "msi": 100,
    },
    "gaming": {
        "asus": 10,
        "msi": 20,
        "nvidia": 30,
        "amd": 40,
        "intel": 50,
        "realtek": 60,
        "dell": 70,
        "hp": 80,
        "lenovo": 90,
        "acer": 100,
    },
    "creative": {
        "dell": 10,
        "hp": 20,
        "nvidia": 30,
        "intel": 40,
        "amd": 50,
        "lenovo": 60,
        "asus": 70,
        "acer": 80,
        "msi": 90,
        "realtek": 100,
    },
}


class Command(BaseCommand):
    help = "Seed DriverSource records with segment-specific OEM/component priorities."

    def add_arguments(self, parser):
        parser.add_argument(
            "--segment",
            choices=sorted(SEGMENT_CHOICES) + ["all"],
            default="all",
            help="Seed one segment or all segments.",
        )

    def handle(self, *args, **options):
        segment = options["segment"]
        segments = sorted(SEGMENT_CHOICES) if segment == "all" else [segment]

        created = 0
        updated = 0

        for seg in segments:
            priorities = SEGMENT_PRIORITY_OVERRIDES[seg]
            for source in DEFAULT_SOURCES:
                defaults = {
                    "vendor_name": source["vendor_name"],
                    "source_type": source["source_type"],
                    "match_terms": ",".join(source["match_terms"]),
                    "support_url": source["support_url"],
                    "driver_url": source["driver_url"],
                    "troubleshooting_url": source["troubleshooting_url"],
                    "priority": priorities.get(source["key"], 999),
                    "is_active": True,
                }
                obj, was_created = DriverSource.objects.update_or_create(
                    key=source["key"],
                    customer_segment=seg,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"DriverSource seed complete: created={created}, updated={updated}, segments={','.join(segments)}"
            )
        )
