import re
from urllib.parse import quote_plus

from diagnostics.models import DriverSource
from diagnostics.services.oem_detection import query_text_matches_msi


DEFAULT_SOURCES = [
    {
        "key": "dell",
        "vendor_name": "Dell",
        "source_type": "oem",
        "match_terms": ["dell", "latitude", "optiplex", "precision", "xps", "alienware"],
        "support_url": "https://www.dell.com/support/home",
        "driver_url": "https://www.dell.com/support/home/drivers",
        "troubleshooting_url": "https://www.dell.com/support/kbdoc/",
    },
    {
        "key": "hp",
        "vendor_name": "HP",
        "source_type": "oem",
        "match_terms": ["hp", "hewlett", "probook", "elitebook", "zbook", "omen"],
        "support_url": "https://support.hp.com/",
        "driver_url": "https://support.hp.com/us-en/drivers",
        "troubleshooting_url": "https://support.hp.com/us-en/help",
    },
    {
        "key": "lenovo",
        "vendor_name": "Lenovo",
        "source_type": "oem",
        "match_terms": ["lenovo", "thinkpad", "thinkcentre", "legion", "yoga"],
        "support_url": "https://support.lenovo.com/",
        "driver_url": "https://support.lenovo.com/us/en/downloads",
        "troubleshooting_url": "https://support.lenovo.com/us/en/solutions",
    },
    {
        "key": "asus",
        "vendor_name": "ASUS",
        "source_type": "oem",
        "match_terms": ["asus", "asustek", "rog", "tuf", "maximus", "strix", "prime"],
        "support_url": "https://www.asus.com/support/",
        "driver_url": "https://www.asus.com/support/download-center/",
        "troubleshooting_url": "https://www.asus.com/support/faq/",
    },
    {
        "key": "acer",
        "vendor_name": "Acer",
        "source_type": "oem",
        "match_terms": ["acer", "nitro", "predator", "swift", "aspire"],
        "support_url": "https://www.acer.com/us-en/support",
        "driver_url": "https://www.acer.com/us-en/support/drivers-and-manuals",
        "troubleshooting_url": "https://www.acer.com/us-en/support/faq",
    },
    {
        "key": "msi",
        "vendor_name": "MSI",
        "source_type": "oem",
        "match_terms": [
            "msi",
            "micro-star",
            "microstar",
            "mag",
            "mpg",
            "meg",
            "tomahawk",
            "mortar",
            "carbon",
            "unify",
            "godlike",
            "bazooka",
        ],
        "support_url": "https://www.msi.com/support",
        "driver_url": "https://www.msi.com/support/download",
        "troubleshooting_url": "https://www.msi.com/faq",
    },
    {
        "key": "intel",
        "vendor_name": "Intel",
        "source_type": "component",
        "match_terms": ["intel", "arc", "core", "iris"],
        "support_url": "https://www.intel.com/content/www/us/en/support.html",
        "driver_url": "https://www.intel.com/content/www/us/en/download-center/home.html",
        "troubleshooting_url": "https://www.intel.com/content/www/us/en/support/articles.html",
    },
    {
        "key": "amd",
        "vendor_name": "AMD",
        "source_type": "component",
        "match_terms": ["amd", "radeon", "ryzen", "threadripper", "epyc"],
        "support_url": "https://www.amd.com/en/support",
        "driver_url": "https://www.amd.com/en/support/download/drivers.html",
        "troubleshooting_url": "https://www.amd.com/en/resources/support-articles.html",
    },
    {
        "key": "nvidia",
        "vendor_name": "NVIDIA",
        "source_type": "component",
        "match_terms": ["nvidia", "geforce", "quadro", "rtx"],
        "support_url": "https://www.nvidia.com/en-us/support/",
        "driver_url": "https://www.nvidia.com/Download/index.aspx",
        "troubleshooting_url": "https://nvidia.custhelp.com/",
    },
    {
        "key": "realtek",
        "vendor_name": "Realtek",
        "source_type": "component",
        "match_terms": ["realtek"],
        "support_url": "https://www.realtek.com/en/",
        "driver_url": "https://www.realtek.com/en/downloads",
        "troubleshooting_url": "https://www.realtek.com/en/contact-us",
    },
]


def _tokenize(text: str) -> set[str]:
    tokens = re.split(r"[^a-z0-9]+", (text or "").lower())
    return {t for t in tokens if t}


def _combined_query(vendor: str, model: str, component: str, hardware_id: str) -> str:
    return " ".join(part for part in [vendor, model, component, hardware_id] if part).strip()


def _from_db(query_tokens: set[str], segment: str = "general") -> list[dict]:
    matches = []
    allowed_segments = {"general", segment or "general"}
    queryset = DriverSource.objects.filter(
        is_active=True,
        customer_segment__in=allowed_segments,
    )
    sources = list(queryset)
    sources.sort(
        key=lambda s: (
            0 if s.customer_segment == segment else 1,
            s.priority,
            s.vendor_name.lower(),
        )
    )
    for source in sources:
        terms = _tokenize(source.match_terms)
        if terms and not (terms & query_tokens):
            continue
        matches.append(
            {
                "key": source.key,
                "vendor_name": source.vendor_name,
                "customer_segment": source.customer_segment,
                "source_type": source.source_type,
                "support_url": source.support_url,
                "driver_url": source.driver_url,
                "troubleshooting_url": source.troubleshooting_url,
                "confidence": "high",
                "source": "custom",
            }
        )
    return matches


def _msi_default_match() -> dict | None:
    source = next((s for s in DEFAULT_SOURCES if s["key"] == "msi"), None)
    if not source:
        return None
    return {
        "key": source["key"],
        "vendor_name": source["vendor_name"],
        "customer_segment": "general",
        "source_type": source["source_type"],
        "support_url": source["support_url"],
        "driver_url": source["driver_url"],
        "troubleshooting_url": source["troubleshooting_url"],
        "confidence": "high",
        "source": "default",
    }


def _from_defaults(query_tokens: set[str], query_text: str = "") -> list[dict]:
    matches = []
    if query_text and query_text_matches_msi(query_text):
        msi = _msi_default_match()
        if msi:
            matches.append(msi)

    for source in DEFAULT_SOURCES:
        if source["key"] == "msi" and any(m["key"] == "msi" for m in matches):
            continue
        terms = set(source["match_terms"])
        if terms & query_tokens:
            matches.append(
                {
                    "key": source["key"],
                    "vendor_name": source["vendor_name"],
                    "customer_segment": "general",
                    "source_type": source["source_type"],
                    "support_url": source["support_url"],
                    "driver_url": source["driver_url"],
                    "troubleshooting_url": source["troubleshooting_url"],
                    "confidence": "medium",
                    "source": "default",
                }
            )
    return matches


def resolve_driver_sources(
    *,
    vendor: str = "",
    model: str = "",
    component: str = "",
    hardware_id: str = "",
    segment: str = "general",
) -> dict:
    query_text = _combined_query(vendor, model, component, hardware_id)
    query_tokens = _tokenize(query_text)

    custom_matches = _from_db(query_tokens, segment=segment)
    default_matches = _from_defaults(query_tokens, query_text)

    merged = []
    seen = set()
    for match in custom_matches + default_matches:
        if match["key"] in seen:
            continue
        seen.add(match["key"])
        merged.append(match)

    generic_search = None
    if query_text:
        q = quote_plus(query_text)
        generic_search = {
            "microsoft_catalog": f"https://www.catalog.update.microsoft.com/Search.aspx?q={q}",
            "microsoft_learn": f"https://learn.microsoft.com/en-us/search/?terms={q}",
        }

    return {
        "query": {
            "vendor": vendor,
            "model": model,
            "component": component,
            "hardware_id": hardware_id,
            "segment": segment,
            "query_text": query_text,
        },
        "matches": merged,
        "generic_search": generic_search,
    }
