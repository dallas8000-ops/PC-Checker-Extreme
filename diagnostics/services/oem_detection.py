"""OEM / motherboard brand inference (MSI is common — WMI often omits the vendor name)."""
import re

# WMI / registry manufacturer strings for MSI boards
MSI_MANUFACTURER_HINTS = (
    "micro-star",
    "micro star",
    "microstar",
    "mirco-star",
    "msi co",
    "msi notebook",
    "micro-star international",
)

# Board product lines and internal model codes (e.g. MS-7C56, MAG B550 TOMAHAWK)
MSI_PRODUCT_RE = re.compile(
    r"(?:"
    r"\bms-\d[a-z0-9]*"  # internal codes e.g. MS-7C56, MS-7D25
    r"|\b(?:mag|mpg|meg)[\s_-]"
    r"|\bpro[\s_-]?(?:b|x|z|h)\d{3,4}"
    r"|\b(?:b|x|z|h)\d{3,4}[\s_-]?(?:gaming|tomahawk|mortar|carbon|wifi|a|m)\b"
    r"|\b(?:tomahawk|mortar|bazooka|unify|godlike|ace)\b"
    r")",
    re.IGNORECASE,
)


def is_msi_motherboard(manufacturer: str = "", product: str = "") -> bool:
    combined = f"{manufacturer or ''} {product or ''}".lower()
    if not combined.strip():
        return False
    if any(hint in combined for hint in MSI_MANUFACTURER_HINTS):
        return True
    if re.search(r"\bmsi\b", combined):
        return True
    return bool(MSI_PRODUCT_RE.search(combined))


def query_text_matches_msi(query_text: str) -> bool:
    return is_msi_motherboard(query_text, "")


def infer_motherboard_brand(manufacturer: str = "", product: str = "") -> str:
    """Return canonical brand name when WMI only exposes a product code or generic OEM text."""
    mfr = (manufacturer or "").strip()
    prod = (product or "").strip()
    lower_mfr = mfr.lower()

    if is_msi_motherboard(mfr, prod):
        return "MSI"
    if "asustek" in lower_mfr or lower_mfr.startswith("asus") or "rog " in prod.lower():
        return "ASUS"
    if "gigabyte" in lower_mfr or "aorus" in prod.lower():
        return "Gigabyte"
    if "asrock" in lower_mfr:
        return "ASRock"
    if "micro-star" in lower_mfr or lower_mfr == "msi":
        return "MSI"

    return ""


def normalize_board_brand(name: str) -> str:
    if not name:
        return ""
    text = str(name).strip()
    inferred = infer_motherboard_brand(text, "")
    if inferred:
        return inferred
    return text
