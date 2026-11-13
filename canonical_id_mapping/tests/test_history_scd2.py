import unittest
import sqlite3
from src.database.repository import CanonicalRepository
from src.pipeline.history_tracker import HistoryTracker
from src.matching.normalizers import build_normalized_record
from src.models.entities import MatchResult

class TestHistorySCD2(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        with open("src/database/schema.sql", "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.repo = CanonicalRepository(self.conn)
        self.tracker = HistoryTracker(self.repo)

        # Seed canonical entities
        self.repo.insert_canonical_entity({
            "canonical_id": "CAN-001",
            "primary_name": "Test User",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        })
        self.repo.insert_canonical_entity({
            "canonical_id": "CAN-002",
            "primary_name": "Reclassified User",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        })

    def tearDown(self):
        self.conn.close()

    def test_initial_mapping_and_history_creation(self):
        norm = build_normalized_record({"source_system": "salesforce", "source_record_id": "SF_101"})
        match = MatchResult(
            source_system="salesforce",
            source_record_id="SF_101",
            canonical_id="CAN-001",
            match_type="RULE_EMAIL",
            matched_rule="rule_email_match",
            confidence_score=0.95
        )

        action = self.tracker.apply_mapping(norm, match, run_id="run_1", current_time_iso="2026-01-01T10:00:00Z")
        self.assertEqual(action, "INITIAL")

        active = self.repo.get_active_mapping("salesforce", "SF_101")
        self.assertIsNotNone(active)
        self.assertEqual(active["canonical_id"], "CAN-001")
        self.assertEqual(active["is_active"], 1)

        history = self.repo.get_mapping_history("salesforce", "SF_101")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["canonical_id"], "CAN-001")
        self.assertEqual(history[0]["is_current"], 1)
        self.assertIsNone(history[0]["effective_to"])
        self.assertEqual(history[0]["change_reason"], "INITIAL_MAPPING")

    def test_idempotent_reobservation_does_not_duplicate_history(self):
        norm = build_normalized_record({"source_system": "salesforce", "source_record_id": "SF_101"})
        match = MatchResult(
            source_system="salesforce",
            source_record_id="SF_101",
            canonical_id="CAN-001",
            match_type="RULE_EMAIL",
            confidence_score=0.95
        )

        self.tracker.apply_mapping(norm, match, run_id="run_1", current_time_iso="2026-01-01T10:00:00Z")
        # Re-run same mapping
        action2 = self.tracker.apply_mapping(norm, match, run_id="run_2", current_time_iso="2026-01-02T10:00:00Z")
        self.assertEqual(action2, "UNCHANGED")

        history = self.repo.get_mapping_history("salesforce", "SF_101")
        self.assertEqual(len(history), 1)  # No redundant history row inserted!

    def test_reclassification_creates_scd2_intervals(self):
        norm = build_normalized_record({"source_system": "salesforce", "source_record_id": "SF_101"})
        match1 = MatchResult(
            source_system="salesforce",
            source_record_id="SF_101",
            canonical_id="CAN-001",
            match_type="RULE_EMAIL",
            confidence_score=0.95
        )
        self.tracker.apply_mapping(norm, match1, run_id="run_1", current_time_iso="2026-01-01T10:00:00Z")

        # Now reclassification occurs to CAN-002
        match2 = MatchResult(
            source_system="salesforce",
            source_record_id="SF_101",
            canonical_id="CAN-002",
            match_type="EXACT_NATIONAL_ID",
            confidence_score=1.0
        )
        action_update = self.tracker.apply_mapping(norm, match2, run_id="run_2", current_time_iso="2026-02-01T10:00:00Z")
        self.assertEqual(action_update, "UPDATED")

        # Active mapping must point to CAN-002
        active = self.repo.get_active_mapping("salesforce", "SF_101")
        self.assertEqual(active["canonical_id"], "CAN-002")

        # History must contain exactly 2 records: old closed interval, new open interval
        history = self.repo.get_mapping_history("salesforce", "SF_101")
        self.assertEqual(len(history), 2)

        # Interval 1 (Closed)
        self.assertEqual(history[0]["canonical_id"], "CAN-001")
        self.assertEqual(history[0]["is_current"], 0)
        self.assertEqual(history[0]["effective_from"], "2026-01-01T10:00:00Z")
        self.assertEqual(history[0]["effective_to"], "2026-02-01T10:00:00Z")

        # Interval 2 (Current)
        self.assertEqual(history[1]["canonical_id"], "CAN-002")
        self.assertEqual(history[1]["is_current"], 1)
        self.assertEqual(history[1]["effective_from"], "2026-02-01T10:00:00Z")
        self.assertIsNone(history[1]["effective_to"])
        self.assertEqual(history[1]["change_reason"], "CANONICAL_RECLASSIFICATION")

if __name__ == "__main__":
    unittest.main()

