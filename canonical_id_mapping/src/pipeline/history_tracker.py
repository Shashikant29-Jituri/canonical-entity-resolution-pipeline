from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from ..database.repository import CanonicalRepository
from ..models.entities import NormalizedRecord, MatchResult

class HistoryTracker:
    """
    Manages SCD Type 2 transitions and audit history for source-to-canonical mappings.
    Guarantees idempotency on reruns by avoiding duplicate history entries when state is unchanged.
    """

    def __init__(self, repo: CanonicalRepository):
        self.repo = repo

    def apply_mapping(
        self,
        record: NormalizedRecord,
        match: MatchResult,
        run_id: str,
        current_time_iso: Optional[str] = None
    ) -> str:
        """
        Applies mapping updates to active mapping table and SCD2 history.
        Returns action taken: 'INITIAL', 'UPDATED', or 'UNCHANGED'.
        """
        now_iso = current_time_iso or datetime.now(timezone.utc).isoformat()
        source_system = record.source_system
        source_record_id = record.source_record_id
        target_canonical_id = match.canonical_id

        if not target_canonical_id:
            raise ValueError(f"Cannot apply mapping without canonical_id for {source_system}:{source_record_id}")

        existing = self.repo.get_active_mapping(source_system, source_record_id)

        if existing is None:
            # Case 1: Brand new mapping
            self.repo.upsert_mapping({
                "source_system": source_system,
                "source_record_id": source_record_id,
                "canonical_id": target_canonical_id,
                "match_type": match.match_type or "RULE",
                "matched_rule": match.matched_rule,
                "confidence_score": match.confidence_score,
                "is_active": 1,
                "created_at": now_iso,
                "updated_at": now_iso,
                "last_run_id": run_id,
            })
            self.repo.insert_history({
                "history_id": str(uuid.uuid4()),
                "source_system": source_system,
                "source_record_id": source_record_id,
                "canonical_id": target_canonical_id,
                "match_type": match.match_type or "RULE",
                "matched_rule": match.matched_rule,
                "effective_from": now_iso,
                "effective_to": None,
                "is_current": 1,
                "change_reason": "INITIAL_MAPPING",
                "run_id": run_id,
            })
            return "INITIAL"

        # Case 2: Mapping already exists
        if existing["canonical_id"] == target_canonical_id:
            # Identical canonical ID: update timestamp and run_id without inflating history
            self.repo.upsert_mapping({
                "source_system": source_system,
                "source_record_id": source_record_id,
                "canonical_id": target_canonical_id,
                "match_type": match.match_type or existing["match_type"],
                "matched_rule": match.matched_rule or existing["matched_rule"],
                "confidence_score": match.confidence_score or existing["confidence_score"],
                "is_active": 1,
                "created_at": existing["created_at"],
                "updated_at": now_iso,
                "last_run_id": run_id,
            })
            return "UNCHANGED"

        # Case 3: Reclassification / Changed Canonical ID
        # Close old history interval
        self.repo.close_current_history(source_system, source_record_id, effective_to=now_iso)

        # Open new history interval
        self.repo.insert_history({
            "history_id": str(uuid.uuid4()),
            "source_system": source_system,
            "source_record_id": source_record_id,
            "canonical_id": target_canonical_id,
            "match_type": match.match_type or "RULE",
            "matched_rule": match.matched_rule,
            "effective_from": now_iso,
            "effective_to": None,
            "is_current": 1,
            "change_reason": "CANONICAL_RECLASSIFICATION",
            "run_id": run_id,
        })

        # Update active mapping
        self.repo.upsert_mapping({
            "source_system": source_system,
            "source_record_id": source_record_id,
            "canonical_id": target_canonical_id,
            "match_type": match.match_type or "RULE",
            "matched_rule": match.matched_rule,
            "confidence_score": match.confidence_score,
            "is_active": 1,
            "created_at": existing["created_at"],
            "updated_at": now_iso,
            "last_run_id": run_id,
        })
        return "UPDATED"

