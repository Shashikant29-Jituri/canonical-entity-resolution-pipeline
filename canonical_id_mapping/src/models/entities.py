from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class NormalizedRecord:
    """Represents a validated, sanitized, and normalized record ready for matching."""
    source_system: str
    source_record_id: str
    national_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    normalized_name: Optional[str] = None
    raw_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    event_timestamp: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MatchCandidate:
    """Represents a potential canonical match found by a rule."""
    canonical_id: str
    rule_name: str
    match_type: str  # EXACT_SOURCE_ID, EXACT_NATIONAL_ID, RULE_EMAIL, RULE_PHONE, RULE_COMPOSITE
    confidence: float
    matched_value: str

@dataclass
class MatchResult:
    """Result of running resolution logic on a single normalized record."""
    source_system: str
    source_record_id: str
    canonical_id: Optional[str] = None
    match_type: Optional[str] = None
    matched_rule: Optional[str] = None
    confidence_score: float = 0.0
    is_conflict: bool = False
    conflict_type: Optional[str] = None
    conflict_details: Optional[Dict[str, Any]] = None
    is_new_canonical: bool = False
    is_unresolved: bool = False
    unresolved_reason: Optional[str] = None
    all_candidates: List[MatchCandidate] = field(default_factory=list)

