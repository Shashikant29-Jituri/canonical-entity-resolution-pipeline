import unittest
import os
import json
import sqlite3
from unittest.mock import patch

from src.database.connection import init_db, get_connection, get_db_context
from src.database.repository import CanonicalRepository
from src.pipeline.runner import execute_pipeline
from src.pipeline.processor import CanonicalPipelineProcessor

class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self.db_path = "data/test_edge_cases.db"
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        init_db(self.db_path)

    def tearDown(self):
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm"]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_empty_batch(self):
        """Pipeline should handle an empty file cleanly with 0 counts and success status."""
        empty_file = "data/test_empty.json"
        with open(empty_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        try:
            metrics = execute_pipeline(input_file=empty_file, db_path=self.db_path, run_id="run_empty_1")
            self.assertEqual(metrics.status, "SUCCESS")
            self.assertEqual(metrics.input_records_count, 0)
            self.assertEqual(metrics.valid_records_count, 0)
            self.assertEqual(metrics.rejected_count, 0)
        finally:
            if os.path.exists(empty_file):
                os.remove(empty_file)

    def test_partial_failure_transaction_rollback(self):
        """
        Simulate an unexpected unhandled database crash midway through a batch.
        The transaction must roll back cleanly, leaving 0 half-baked records in the DB.
        """
        raw_records = [
            {"source_system": "crm", "source_record_id": "CRASH_1", "email": "crash1@example.com"},
            {"source_system": "crm", "source_record_id": "CRASH_2", "email": "crash2@example.com"},
        ]

        def crashing_upsert(*args, **kwargs):
            raise sqlite3.OperationalError("Simulated disk I/O failure")

        with self.assertRaises(sqlite3.OperationalError):
            with get_db_context(self.db_path) as conn:
                repo = CanonicalRepository(conn)
                processor = CanonicalPipelineProcessor(repo=repo)
                with patch.object(repo, "upsert_mapping", side_effect=crashing_upsert):
                    processor.process_batch(raw_records, run_id="run_crash_1")

        # Verify database is intact and uncorrupted (0 records inserted)
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM source_to_canonical_mapping")
        count = cursor.fetchone()["total"]
        conn.close()
        self.assertEqual(count, 0)

    def test_unexpected_extra_schema_fields(self):
        """Input containing additional unexpected fields should still parse cleanly without crashing."""
        test_file = "data/test_extra_fields.json"
        records = [
            {
                "source_system": "legacy_crm",
                "source_record_id": "LEG_99",
                "email": "extra@example.com",
                "first_name": "Extra",
                "last_name": "Fields",
                "random_undocumented_attribute": "some_value",
                "internal_tracking_id": 99999
            }
        ]
        with open(test_file, "w", encoding="utf-8") as f:
            json.dump(records, f)

        try:
            metrics = execute_pipeline(input_file=test_file, db_path=self.db_path, run_id="run_extra_fields")
            self.assertEqual(metrics.status, "SUCCESS")
            self.assertEqual(metrics.valid_records_count, 1)
            self.assertEqual(metrics.created_canonical_count, 1)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_auto_create_canonical_disabled_routes_to_unresolved(self):
        """When auto-create is disabled, novel unmapped entities must be quarantined as unresolved."""
        test_file = "data/test_no_autocreate.json"
        records = [
            {
                "source_system": "crm",
                "source_record_id": "NO_AUTO_1",
                "email": "novel_no_auto@example.com",
                "first_name": "NoAuto",
                "last_name": "Create"
            }
        ]
        with open(test_file, "w", encoding="utf-8") as f:
            json.dump(records, f)

        try:
            metrics = execute_pipeline(
                input_file=test_file,
                db_path=self.db_path,
                run_id="run_no_auto_1",
                auto_create_canonical=False
            )
            self.assertEqual(metrics.unresolved_count, 1)
            self.assertEqual(metrics.created_canonical_count, 0)

            conn = get_connection(self.db_path)
            repo = CanonicalRepository(conn)
            unresolved = repo.get_unresolved_records(run_id="run_no_auto_1")
            conn.close()

            self.assertEqual(len(unresolved), 1)
            self.assertEqual(unresolved[0]["reason_code"], "UNRESOLVED_AUTO_CREATE_DISABLED")
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

if __name__ == "__main__":
    unittest.main()

