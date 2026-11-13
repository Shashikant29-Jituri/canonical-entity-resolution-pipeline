import hashlib
import uuid
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone

from ..models.entities import NormalizedRecord, MatchCandidate, MatchResult
from ..database.repository import CanonicalRepository
from .rules import (
    BaseMatchingRule,
    ExactSourceIdRule,
    ExactNationalIdRule,
    EmailRule,
    PhoneRule,
    CompositeNamePostalRule
)
from .conflict_detector import ConflictDetector

class MatchingEngine:
    """
    Core Entity Resolution & Matching Engine.
    Orchestrates tiered rules, conflict detection, novel canonical creation,
    and confidence scoring.
    """

    def __init__(
        self,
        repo: CanonicalRepository,
        rules: Optional[List[BaseMatchingRule]] = None,
        auto_create_canonical: bool = True,
        min_confidence_threshold: float = 0.70
    ):
        self.repo = repo
        self.auto_create_canonical = auto_create_canonical
        self.min_confidence_threshold = min_confidence_threshold
        self.rules = rules or [
            ExactSourceIdRule(),
            ExactNationalIdRule(),
            EmailRule(),
            PhoneRule(),
            CompositeNamePostalRule()
        ]

    def _generate_canonical_id(self, record: NormalizedRecord) -> str:
        """
        Generates a stable, deterministic canonical ID using a SHA-256 hash
        of the primary natural identity seed.
        """
        seed = record.national_id or record.email or record.phone or f"{record.normalized_name}|{record.postal_code}"
        if not seed:
            seed = f"{record.source_system}:{record.source_record_id}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()
        return f"CAN-{digest}"

    def _has_sufficient_attributes_for_new_entity(self, record: NormalizedRecord) -> bool:
        """Checks if a record contains sufficient attributes to establish a distinct entity."""
        if record.national_id:
            return True
        if record.email:
            return True
        if record.phone:
            return True
        if record.normalized_name and record.postal_code:
            return True
        return False

    def resolve(self, record: NormalizedRecord) -> MatchResult:
        """
        Executes full resolution pipeline for a single normalized record.
        """
        all_candidates: List[MatchCandidate] = []

        # Evaluate all configured rules to detect potential multi-attribute divergence
        for rule in self.rules:
            candidates = rule.evaluate(record, self.repo)
            all_candidates.extend(candidates)

        # Step 1: Check for conflicts among all candidates
        is_conflict, conflict_type, conflict_details = ConflictDetector.analyze_candidates(
            record, all_candidates
        )

        if is_conflict:
            return MatchResult(
                source_system=record.source_system,
                source_record_id=record.source_record_id,
                canonical_id=None,
                match_type=None,
                matched_rule=None,
                confidence_score=0.0,
                is_conflict=True,
                conflict_type=conflict_type,
                conflict_details=conflict_details,
                is_new_canonical=False,
                is_unresolved=True,
                unresolved_reason=conflict_type,
                all_candidates=all_candidates
            )

        # Step 2: Single or unanimous candidate found
        if all_candidates:
            # Sort candidates by confidence descending
            best_candidate = max(all_candidates, key=lambda c: c.confidence)
            if best_candidate.confidence >= self.min_confidence_threshold:
                return MatchResult(
                    source_system=record.source_system,
                    source_record_id=record.source_record_id,
                    canonical_id=best_candidate.canonical_id,
                    match_type=best_candidate.match_type,
                    matched_rule=best_candidate.rule_name,
                    confidence_score=best_candidate.confidence,
                    is_conflict=False,
                    is_new_canonical=False,
                    is_unresolved=False,
                    all_candidates=all_candidates
                )

        # Step 3: No candidates found - evaluate for novel canonical creation
        if self._has_sufficient_attributes_for_new_entity(record):
            if self.auto_create_canonical:
                new_canonical_id = self._generate_canonical_id(record)
                return MatchResult(
                    source_system=record.source_system,
                    source_record_id=record.source_record_id,
                    canonical_id=new_canonical_id,
                    match_type="NEW_CANONICAL",
                    matched_rule="auto_provision_novel_entity",
                    confidence_score=1.0,
                    is_conflict=False,
                    is_new_canonical=True,
                    is_unresolved=False,
                    all_candidates=[]
                )
            else:
                return MatchResult(
                    source_system=record.source_system,
                    source_record_id=record.source_record_id,
                    is_conflict=False,
                    is_unresolved=True,
                    unresolved_reason="UNRESOLVED_AUTO_CREATE_DISABLED",
                    all_candidates=[]
                )

        # Step 4: Insufficient attributes to match or create entity
        return MatchResult(
            source_system=record.source_system,
            source_record_id=record.source_record_id,
            is_conflict=False,
            is_unresolved=True,
            unresolved_reason="UNRESOLVED_INSUFFICIENT_ATTRIBUTES",
            conflict_details={"message": "Record lacks required identifiers (no valid email, phone, SSN, or name+zip)"},
            all_candidates=[]
        )

