import unittest
import os
import json
import sqlite3
from src.database.connection import init_db, get_connection
from src.pipeline.runner import execute_pipeline
from src.database.repository import CanonicalRepository

class TestIdempotencyAndRerun(unittest.TestCase):
    def setUp(self):
        self.db_path = "data/test_idempotency.db"
        self.sample_file = "data/test_sample.json"
        
        # Ensure fresh start
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm", self.sample_file]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        records = [
            {
                "source_system": "crm_salesforce",
                "source_record_id": "SF_IDEM_1",
                "email": "idem1@example.com",
                "first_name": "Idem",
                "last_name": "One",
                "postal_code": "94101"
            },
            {
                "source_system": "billing_stripe",
                "source_record_id": "STRIPE_IDEM_2",
                "email": "idem1@example.com",  # Should map to same entity
                "first_name": "Idem",
                "last_name": "One",
                "postal_code": "94101"
            }
        ]
        with open(self.sample_file, "w", encoding="utf-8") as f:
            json.dump(records, f)

    def tearDown(self):
        for p in [self.db_path, f"{self.db_path}-wal", f"{self.db_path}-shm", self.sample_file]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    def test_idempotent_multiple_runs(self):
        # Run 1
        m1 = execute_pipeline(input_file=self.sample_file, db_path=self.db_path, run_id="run_101")
        self.assertEqual(m1.valid_records_count, 2)
        self.assertEqual(m1.created_canonical_count, 1)
        self.assertEqual(m1.mapped_existing_count, 1)

        conn = get_connection(self.db_path)
        repo = CanonicalRepository(conn)
        recon1 = repo.get_reconciliation_summary()
        conn.close()

        self.assertEqual(recon1["total_canonical_entities"], 1)
        self.assertEqual(recon1["total_active_mappings"], 2)
        self.assertEqual(recon1["total_history_records"], 2)

        # Run 2 (Rerun identical input)
        m2 = execute_pipeline(input_file=self.sample_file, db_path=self.db_path, run_id="run_102")
        self.assertEqual(m2.valid_records_count, 2)

        conn = get_connection(self.db_path)
        repo = CanonicalRepository(conn)
        recon2 = repo.get_reconciliation_summary()
        conn.close()

        # The counts MUST be identical after rerun! No duplicate mappings, no duplicate entities!
        self.assertEqual(recon2["total_canonical_entities"], 1)
        self.assertEqual(recon2["total_active_mappings"], 2)
        self.assertEqual(recon2["total_history_records"], 2)
        self.assertEqual(recon2["orphan_mappings_count"], 0)

if __name__ == "__main__":
    unittest.main()

