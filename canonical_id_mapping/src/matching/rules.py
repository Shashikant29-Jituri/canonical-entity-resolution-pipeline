from abc import ABC, abstractmethod
from typing import List, Optional
from ..models.entities import NormalizedRecord, MatchCandidate
from ..database.repository import CanonicalRepository

class BaseMatchingRule(ABC):
    """Abstract base class for all deterministic and rule-based matchers."""
    name: str = "base_rule"
    match_type: str = "RULE"
    default_confidence: float = 0.80

    @abstractmethod
    def evaluate(self, record: NormalizedRecord, repo: CanonicalRepository) -> List[MatchCandidate]:
        """Evaluates the record against target repository and returns all candidate matches."""
        pass

class ExactSourceIdRule(BaseMatchingRule):
    """Rule 0: Exact match on source system + source record ID."""
    name = "exact_source_id_rule"
    match_type = "EXACT_SOURCE_ID"
    default_confidence = 1.0

    def evaluate(self, record: NormalizedRecord, repo: CanonicalRepository) -> List[MatchCandidate]:
        existing = repo.get_active_mapping(record.source_system, record.source_record_id)
        if existing and existing.get("canonical_id"):
            return [
                MatchCandidate(
                    canonical_id=existing["canonical_id"],
                    rule_name=self.name,
                    match_type=self.match_type,
                    confidence=self.default_confidence,
                    matched_value=f"{record.source_system}:{record.source_record_id}"
                )
            ]
        return []

class ExactNationalIdRule(BaseMatchingRule):
    """Rule 1: Exact match on National Tax ID / SSN."""
    name = "exact_national_id_rule"
    match_type = "EXACT_NATIONAL_ID"
    default_confidence = 1.0

    def evaluate(self, record: NormalizedRecord, repo: CanonicalRepository) -> List[MatchCandidate]:
        if not record.national_id:
            return []
        canonical_ids = repo.find_canonical_by_national_id(record.national_id)
        return [
            MatchCandidate(
                canonical_id=cid,
                rule_name=self.name,
                match_type=self.match_type,
                confidence=self.default_confidence,
                matched_value=record.national_id
            )
            for cid in canonical_ids
        ]

class EmailRule(BaseMatchingRule):
    """Rule 2: Match on normalized email address."""
    name = "rule_email_match"
    match_type = "RULE_EMAIL"
    default_confidence = 0.95

    def evaluate(self, record: NormalizedRecord, repo: CanonicalRepository) -> List[MatchCandidate]:
        if not record.email:
            return []
        canonical_ids = repo.find_canonical_by_email(record.email)
        return [
            MatchCandidate(
                canonical_id=cid,
                rule_name=self.name,
                match_type=self.match_type,
                confidence=self.default_confidence,
                matched_value=record.email
            )
            for cid in canonical_ids
        ]

class PhoneRule(BaseMatchingRule):
    """Rule 3: Match on normalized phone number."""
    name = "rule_phone_match"
    match_type = "RULE_PHONE"
    default_confidence = 0.90

    def evaluate(self, record: NormalizedRecord, repo: CanonicalRepository) -> List[MatchCandidate]:
        if not record.phone:
            return []
        canonical_ids = repo.find_canonical_by_phone(record.phone)
        return [
            MatchCandidate(
                canonical_id=cid,
                rule_name=self.name,
                match_type=self.match_type,
                confidence=self.default_confidence,
                matched_value=record.phone
            )
            for cid in canonical_ids
        ]

class CompositeNamePostalRule(BaseMatchingRule):
    """Rule 4: Composite match on Normalized Name + Postal Code."""
    name = "rule_composite_name_postal"
    match_type = "RULE_COMPOSITE"
    default_confidence = 0.85

    def evaluate(self, record: NormalizedRecord, repo: CanonicalRepository) -> List[MatchCandidate]:
        if not record.normalized_name or not record.postal_code:
            return []
        canonical_ids = repo.find_canonical_by_composite(record.normalized_name, record.postal_code)
        return [
            MatchCandidate(
                canonical_id=cid,
                rule_name=self.name,
                match_type=self.match_type,
                confidence=self.default_confidence,
                matched_value=f"{record.normalized_name}|{record.postal_code}"
            )
            for cid in canonical_ids
        ]

