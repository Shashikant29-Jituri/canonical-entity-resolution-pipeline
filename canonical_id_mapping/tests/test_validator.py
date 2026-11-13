import unittest
from src.pipeline.validator import PipelineValidator

class TestPipelineValidator(unittest.TestCase):
    def test_valid_record(self):
        batch = [
            {
                "source_system": "salesforce",
                "source_record_id": "SF_101",
                "email": "user@example.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "date_of_birth": "1990-01-01"
            }
        ]
        res = PipelineValidator.validate_batch(batch, run_id="run_test_1")
        self.assertEqual(len(res.valid_records), 1)
        self.assertEqual(len(res.quarantined_records), 0)
        self.assertEqual(res.duplicate_count, 0)
        self.assertEqual(res.valid_records[0].source_system, "salesforce")

    def test_missing_required_keys(self):
        # Missing source_system
        batch = [{"source_record_id": "SF_101", "email": "test@example.com"}]
        res = PipelineValidator.validate_batch(batch, run_id="run_test_2")
        self.assertEqual(len(res.valid_records), 0)
        self.assertEqual(len(res.quarantined_records), 1)
        self.assertEqual(res.quarantined_records[0]["reason_code"], "MISSING_REQUIRED_KEY")

        # Blank/empty source_record_id
        batch2 = [{"source_system": "salesforce", "source_record_id": "   "}]
        res2 = PipelineValidator.validate_batch(batch2, run_id="run_test_3")
        self.assertEqual(len(res2.valid_records), 0)
        self.assertEqual(len(res2.quarantined_records), 1)
        self.assertIn(res2.quarantined_records[0]["reason_code"], ["MISSING_REQUIRED_KEY", "SCHEMA_VALIDATION_ERROR"])

    def test_malformed_input_type(self):
        # Item is not a dict
        batch = ["not_a_json_dict", 12345]
        res = PipelineValidator.validate_batch(batch, run_id="run_test_4")
        self.assertEqual(len(res.valid_records), 0)
        self.assertEqual(len(res.quarantined_records), 2)
        self.assertEqual(res.quarantined_records[0]["reason_code"], "MALFORMED_INPUT")

    def test_invalid_date_format(self):
        batch = [{
            "source_system": "crm",
            "source_record_id": "C_1",
            "date_of_birth": "31/12/1990"  # Invalid format
        }]
        res = PipelineValidator.validate_batch(batch, run_id="run_test_5")
        self.assertEqual(len(res.valid_records), 0)
        self.assertEqual(len(res.quarantined_records), 1)
        self.assertEqual(res.quarantined_records[0]["reason_code"], "SCHEMA_VALIDATION_ERROR")

    def test_intra_batch_identical_duplicate(self):
        rec = {
            "source_system": "crm",
            "source_record_id": "DUP_1",
            "email": "dup@example.com",
            "first_name": "Bob"
        }
        batch = [rec, rec]  # Identical duplicate in same batch
        res = PipelineValidator.validate_batch(batch, run_id="run_test_6")
        self.assertEqual(len(res.valid_records), 1)
        self.assertEqual(res.duplicate_count, 1)
        self.assertEqual(len(res.quarantined_records), 0)

    def test_intra_batch_key_collision_conflicting_attributes(self):
        batch = [
            {"source_system": "crm", "source_record_id": "COL_1", "email": "a@example.com"},
            {"source_system": "crm", "source_record_id": "COL_1", "email": "b@example.com"}  # Conflicting email
        ]
        res = PipelineValidator.validate_batch(batch, run_id="run_test_7")
        self.assertEqual(len(res.valid_records), 1)
        self.assertEqual(len(res.quarantined_records), 1)
        self.assertEqual(res.quarantined_records[0]["reason_code"], "CONFLICT_SOURCE_KEY_COLLISION")

if __name__ == "__main__":
    unittest.main()

