from .normalizers import (
    normalize_email,
    normalize_phone,
    normalize_name,
    normalize_national_id,
    normalize_postal_code,
    build_normalized_record
)
from .rules import (
    BaseMatchingRule,
    ExactSourceIdRule,
    ExactNationalIdRule,
    EmailRule,
    PhoneRule,
    CompositeNamePostalRule
)
from .conflict_detector import ConflictDetector
from .engine import MatchingEngine

__all__ = [
    "normalize_email",
    "normalize_phone",
    "normalize_name",
    "normalize_national_id",
    "normalize_postal_code",
    "build_normalized_record",
    "BaseMatchingRule",
    "ExactSourceIdRule",
    "ExactNationalIdRule",
    "EmailRule",
    "PhoneRule",
    "CompositeNamePostalRule",
    "ConflictDetector",
    "MatchingEngine"
]

