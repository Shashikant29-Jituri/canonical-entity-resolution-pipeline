from typing import List, Dict, Any, Optional, Tuple
from ..models.entities import MatchCandidate, MatchResult, NormalizedRecord

class ConflictDetector:
    """
    Detects one-to-many ambiguity, cross-rule identity splits,
    and multi-candidate collisions.
    """

    @staticmethod
    def analyze_candidates(
        record: NormalizedRecord,
        candidates: List[MatchCandidate]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Analyzes a list of match candidates for a single record.
        Returns: (is_conflict, conflict_reason_code, conflict_details)
        """
        if not candidates:
            return False, None, None

        # Collect unique canonical IDs across all candidates
        unique_cids = {c.canonical_id for c in candidates}

        # Case 1: Check if any individual rule produced multiple candidate matches
        # (e.g. Composite rule matched 2 different people with the same name and zip)
        rule_candidate_counts: Dict[str, int] = {}
        for c in candidates:
            rule_candidate_counts[c.rule_name] = rule_candidate_counts.get(c.rule_name, 0) + 1

        for rule_name, count in rule_candidate_counts.items():
            if count > 1:
                details = {
                    "rule_name": rule_name,
                    "candidate_count": count,
                    "matched_candidates": [
                        {"canonical_id": c.canonical_id, "matched_value": c.matched_value}
                        for c in candidates if c.rule_name == rule_name
                    ],
                    "message": f"Rule '{rule_name}' resolved to {count} candidate entities; match is ambiguous."
                }
                return True, "CONFLICT_AMBIGUOUS_RULE_MATCH", details

        # Case 2: Multiple distinct Canonical IDs returned across different rules
        # (e.g. Email rule matched Canonical A, but Phone rule matched Canonical B)
        if len(unique_cids) > 1:
            details = {
                "conflicting_canonical_ids": list(unique_cids),
                "matched_rules": [
                    {
                        "canonical_id": c.canonical_id,
                        "rule_name": c.rule_name,
                        "match_type": c.match_type,
                        "matched_value": c.matched_value,
                        "confidence": c.confidence,
                    }
                    for c in candidates
                ],
                "message": f"Source record matches {len(unique_cids)} distinct canonical entities across rules."
            }
            return True, "CONFLICT_ONE_TO_MANY_CANONICAL", details

        return False, None, None
