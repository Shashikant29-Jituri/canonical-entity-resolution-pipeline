import unittest
import sqlite3
from src.database.connection import init_db, get_connection
from src.database.repository import CanonicalRepository
from src.matching.engine import MatchingEngine
from src.matching.normalizers import build_normalized_record
from src.matching.conflict_detector import ConflictDetector

class TestConflictDetection(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        with open("src/database/schema.sql", "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.repo = CanonicalRepository(self.conn)
        self.engine = MatchingEngine(self.repo)

        # Pre-populate two distinct canonical entities
        self.repo.insert_canonical_entity({
            "canonical_id": "CAN-A",
            "primary_name": "alice smith",
            "primary_email": "alice@example.com",
            "primary_phone": "5551111",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        })
        self.repo.insert_canonical_entity({
            "canonical_id": "CAN-B",
            "primary_name": "bob jones",
            "primary_email": "bob@example.com",
            "primary_phone": "5552222",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        })

    def tearDown(self):
        self.conn.close()

    def test_one_to_many_cross_rule_conflict(self):
        """
        Record has email matching CAN-A, but phone matching CAN-B.
        Should detect CONFLICT_ONE_TO_MANY_CANONICAL and NOT arbitrarily pick one.
        """
        record_dict = {
            "source_system": "crm",
            "source_record_id": "SRC_CONFLICT_1",
            "email": "alice@example.com",  # matches CAN-A
            "phone": "555-2222",            # matches CAN-B
            "first_name": "Conflicted",
            "last_name": "Record"
        }
        norm = build_normalized_record(record_dict)
        res = self.engine.resolve(norm)

        self.assertTrue(res.is_conflict)
        self.assertTrue(res.is_unresolved)
        self.assertEqual(res.conflict_type, "CONFLICT_ONE_TO_MANY_CANONICAL")
        self.assertIsNone(res.canonical_id)
        self.assertEqual(len(res.conflict_details["conflicting_canonical_ids"]), 2)
        self.assertIn("CAN-A", res.conflict_details["conflicting_canonical_ids"])
        self.assertIn("CAN-B", res.conflict_details["conflicting_canonical_ids"])

    def test_ambiguous_composite_rule_match(self):
        """
        Two distinct canonical entities have the exact same name and postal code.
        Incoming record with only name and postal code should trigger CONFLICT_AMBIGUOUS_RULE_MATCH.
        """
        self.repo.insert_canonical_entity({
            "canonical_id": "CAN-C1",
            "primary_name": "charlie brown",
            "primary_email": "c1@example.com",
            "postal_code": "90210",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        })
        self.repo.insert_canonical_entity({
            "canonical_id": "CAN-C2",
            "primary_name": "charlie brown",
            "primary_email": "c2@example.com",
            "postal_code": "90210",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        })

        record_dict = {
            "source_system": "crm",
            "source_record_id": "SRC_AMBIG_1",
            "first_name": "Charlie",
            "last_name": "Brown",
            "postal_code": "90210"
        }
        norm = build_normalized_record(record_dict)
        res = self.engine.resolve(norm)

        self.assertTrue(res.is_conflict)
        self.assertEqual(res.conflict_type, "CONFLICT_AMBIGUOUS_RULE_MATCH")
        self.assertIsNone(res.canonical_id)

if __name__ == "__main__":
    unittest.main()

