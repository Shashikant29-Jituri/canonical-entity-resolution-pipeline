import re
from typing import Optional, Tuple, Dict, Any
from ..models.entities import NormalizedRecord

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def normalize_email(email: Optional[str]) -> Optional[str]:
    """Standardizes email addresses: lowercase, stripped, basic validation."""
    if not email:
        return None
    cleaned = email.strip().lower()
    if not cleaned or not EMAIL_REGEX.match(cleaned):
        return None
    return cleaned

def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Extracts numeric digits from phone numbers; handles standard formats."""
    if not phone:
        return None
    raw = phone.strip()
    if raw.startswith("+1"):
        raw = raw[2:]
    digits = re.sub(r"\D", "", raw)
    # If 11 digits and starts with 1 (US country code), normalize to 10 digits
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) < 7:  # Invalid phone length
        return None
    return digits

def normalize_name(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    legal_name: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalizes personal/entity name for deterministic comparison.
    Returns (normalized_clean_name, raw_display_name).
    """
    raw_name = ""
    if legal_name and legal_name.strip():
        raw_name = legal_name.strip()
    elif first_name or last_name:
        parts = [p.strip() for p in (first_name, last_name) if p and p.strip()]
        raw_name = " ".join(parts)

    if not raw_name:
        return None, None

    # Normalization: lowercased, remove punctuation, remove common business affixes
    cleaned = raw_name.lower()
    cleaned = re.sub(r"[,\.\'\"]", "", cleaned)
    # Remove business affixes
    affixes = [r"\binc\b", r"\bllc\b", r"\bcorp\b", r"\bcorporation\b", r"\bltd\b", r"\bco\b"]
    for affix in affixes:
        cleaned = re.sub(affix, "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned if cleaned else None, raw_name

def normalize_national_id(national_id: Optional[str]) -> Optional[str]:
    """Normalizes SSN / Tax ID / National ID by stripping hyphens, spaces, and uppercasing."""
    if not national_id:
        return None
    cleaned = re.sub(r"[\s\-_]", "", national_id.strip()).upper()
    return cleaned if cleaned else None

def normalize_postal_code(postal_code: Optional[str]) -> Optional[str]:
    """Normalizes postal/ZIP code to 5-digit or uppercase alphanumeric."""
    if not postal_code:
        return None
    cleaned = postal_code.strip().upper()
    # If US ZIP+4, extract primary 5 digits
    zip5 = re.match(r"^(\d{5})(-\d{4})?$", cleaned)
    if zip5:
        return zip5.group(1)
    return cleaned if cleaned else None

def build_normalized_record(raw: Dict[str, Any]) -> NormalizedRecord:
    """Builds a NormalizedRecord dataclass from validated raw input dictionary."""
    norm_name, raw_name = normalize_name(
        raw.get("first_name"),
        raw.get("last_name"),
        raw.get("legal_name")
    )
    return NormalizedRecord(
        source_system=raw["source_system"].strip(),
        source_record_id=str(raw["source_record_id"]).strip(),
        national_id=normalize_national_id(raw.get("national_id")),
        email=normalize_email(raw.get("email")),
        phone=normalize_phone(raw.get("phone")),
        normalized_name=norm_name,
        raw_name=raw_name,
        date_of_birth=raw.get("date_of_birth"),
        postal_code=normalize_postal_code(raw.get("postal_code")),
        country=raw.get("country", "").strip().upper() if raw.get("country") else None,
        event_timestamp=raw.get("event_timestamp"),
        raw_payload=raw,
    )
