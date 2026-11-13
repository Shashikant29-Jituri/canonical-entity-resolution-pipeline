import unittest
import os
import json
import sqlite3
from pathlib import Path

from src.database.connection import init_db, get_connection
from src.database.repository import CanonicalRepository
from scripts.run_pipeline import seed_canonical_registry
from src.pipeline.runner import execute_pipeline
from scripts.run_reconciliation import generate_reconciliation_report

class TestEndToEndPipeline(unittest.TestCase):
    def setUp(self):
        self.db_path = "data/test_e2e.db"
        self.sample_input = "data/sample/source_records_sample.json"
        self.seed_file = "data/sample/seed_canonical_entities.json"
        self.expected_file = "data/sample/expected_results.json"

        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        init_db(self.db_path)
        seed_canonical_registry(self.db_path, self.seed_file)

    def tearDown(self):
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_e2e_execution_and_expected_results(self):
        run_id = "test_e2e_run_001"
        metrics = execute_pipeline(
            input_file=self.sample_input,
            db_path=self.db_path,
            run_id=run_id,
            auto_create_canonical=True
        )

        self.assertEqual(metrics.input_records_count, 11)
        self.assertEqual(metrics.status, "PARTIAL_SUCCESS")

        # Load expected results
        with open(self.expected_file, "r", encoding="utf-8") as f:
            expected_data = json.load(f)

        conn = get_connection(self.db_path)
        repo = CanonicalRepository(conn)

        # 1. Verify Happy Path Matches
        # SF_1001 -> CAN-0001 (SSN match)
        map_sf = repo.get_active_mapping("crm_salesforce", "SF_1001")
        self.assertIsNotNone(map_sf)
        self.assertEqual(map_sf["canonical_id"], "CAN-0001")
        self.assertEqual(map_sf["match_type"], "EXACT_NATIONAL_ID")

        # STRIPE_2001 -> CAN-0001 (Email match)
        map_stripe = repo.get_active_mapping("billing_stripe", "STRIPE_2001")
        self.assertIsNotNone(map_stripe)
        self.assertEqual(map_stripe["canonical_id"], "CAN-0001")
        self.assertEqual(map_stripe["match_type"], "RULE_EMAIL")

        # ZD_3001 -> CAN-0002 (Phone match)
        map_zd = repo.get_active_mapping("support_zendesk", "ZD_3001")
        self.assertIsNotNone(map_zd)
        self.assertEqual(map_zd["canonical_id"], "CAN-0002")
        self.assertEqual(map_zd["match_type"], "RULE_PHONE")

        # SEG_4001 -> Novel Canonical Entity created
        map_seg = repo.get_active_mapping("web_segment", "SEG_4001")
        self.assertIsNotNone(map_seg)
        self.assertTrue(map_seg["canonical_id"].startswith("CAN-"))
        self.assertEqual(map_seg["match_type"], "NEW_CANONICAL")

        # 2. Verify Quarantined / Unresolved Records
        unresolved = repo.get_unresolved_records(run_id=run_id)
        unresolved_by_key = {
            (r["source_system"], r["source_record_id"]): r for r in unresolved
        }

        # SF_CONFLICT_01 -> CONFLICT_ONE_TO_MANY_CANONICAL
        self.assertIn(("crm_salesforce", "SF_CONFLICT_01"), unresolved_by_key)
        self.assertEqual(
            unresolved_by_key[("crm_salesforce", "SF_CONFLICT_01")]["reason_code"],
            "CONFLICT_ONE_TO_MANY_CANONICAL"
        )

        # LEG_AMBIG_01 -> CONFLICT_AMBIGUOUS_RULE_MATCH
        self.assertIn(("legacy_db", "LEG_AMBIG_01"), unresolved_by_key)
        self.assertEqual(
            unresolved_by_key[("legacy_db", "LEG_AMBIG_01")]["reason_code"],
            "CONFLICT_AMBIGUOUS_RULE_MATCH"
        )

        # BAD_DOB_01 -> SCHEMA_VALIDATION_ERROR
        self.assertIn(("bad_feed", "BAD_DOB_01"), unresolved_by_key)
        self.assertEqual(
            unresolved_by_key[("bad_feed", "BAD_DOB_01")]["reason_code"],
            "SCHEMA_VALIDATION_ERROR"
        )

        # Empty source_record_id -> MISSING_REQUIRED_KEY
        self.assertIn(("bad_feed", ""), unresolved_by_key)
        self.assertEqual(
            unresolved_by_key[("bad_feed", "")]["reason_code"],
            "MISSING_REQUIRED_KEY"
        )

        # MOB_EMPTY_ATTRS -> UNRESOLVED_INSUFFICIENT_ATTRIBUTES
        self.assertIn(("mobile_app", "MOB_EMPTY_ATTRS"), unresolved_by_key)
        self.assertEqual(
            unresolved_by_key[("mobile_app", "MOB_EMPTY_ATTRS")]["reason_code"],
            "UNRESOLVED_INSUFFICIENT_ATTRIBUTES"
        )

        # STRIPE_2001 key collision -> CONFLICT_SOURCE_KEY_COLLISION
        self.assertIn(("billing_stripe", "STRIPE_2001"), unresolved_by_key)
        self.assertEqual(
            unresolved_by_key[("billing_stripe", "STRIPE_2001")]["reason_code"],
            "CONFLICT_SOURCE_KEY_COLLISION"
        )

        conn.close()

        # 3. Verify Reconciliation Report
        report = generate_reconciliation_report(self.db_path)
        self.assertTrue(report["checks"]["referential_integrity"]["passed"])
        self.assertTrue(report["checks"]["active_mapping_uniqueness"]["passed"])
        self.assertTrue(report["checks"]["scd2_interval_consistency"]["passed"])
        self.assertEqual(report["checks"]["referential_integrity"]["orphan_active_mappings"], 0)

if __name__ == "__main__":
    unittest.main()

