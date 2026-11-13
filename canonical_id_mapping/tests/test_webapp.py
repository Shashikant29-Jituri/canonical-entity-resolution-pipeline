import unittest
import json
import os
import shutil
from pathlib import Path

# Use dedicated test DB to protect canonical_store.db
TEST_DB_PATH = "data/test_webapp.db"
os.environ["CANONICAL_DB_PATH"] = TEST_DB_PATH

from src.database.connection import init_db
from webapp.app import app, DB_PATH
import webapp.app as webapp_mod
webapp_mod.DB_PATH = TEST_DB_PATH

class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Path(TEST_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        if Path(TEST_DB_PATH).exists():
            try:
                Path(TEST_DB_PATH).unlink()
            except Exception:
                pass
        init_db(TEST_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        if Path(TEST_DB_PATH).exists():
            try:
                Path(TEST_DB_PATH).unlink()
            except Exception:
                pass

    def setUp(self):
        self.client = app.test_client()

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Canonical ID Mapping", response.data)

    def test_api_dashboard(self):
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("summary", data)

    def test_api_mappings(self):
        response = self.client.get("/api/mappings")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIsInstance(data["data"], list)

    def test_api_entities(self):
        response = self.client.get("/api/entities")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")

    def test_api_unresolved(self):
        response = self.client.get("/api/unresolved")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")

    def test_api_ingest_single_live_playground(self):
        payload = {
            "source_system": "live_test_web",
            "source_record_id": "TEST_WEB_01",
            "email": "live.user@example.com",
            "first_name": "Live",
            "last_name": "User",
            "postal_code": "94101"
        }
        response = self.client.post(
            "/api/ingest-single",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("resolved_canonical_id", data)

    def test_api_load_genuine_data(self):
        response = self.client.post("/api/load-genuine-data")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertIn("metrics", data)

    def test_api_upload_multiple_datasets(self):
        import io
        csv_data_1 = "id,name,email,phone\nU101,John Doe,jdoe@test.com,5550111\n"
        csv_data_2 = "id,name,email,phone\nU202,Jane Smith,jsmith@test.com,5550222\n"

        data = {
            "files": [
                (io.BytesIO(csv_data_1.encode("utf-8")), "source_crm.csv"),
                (io.BytesIO(csv_data_2.encode("utf-8")), "source_billing.csv")
            ]
        }

        response = self.client.post("/api/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        res_json = response.get_json()
        self.assertEqual(res_json["status"], "success")
        self.assertEqual(res_json["summary"]["files_processed_count"], 2)
        self.assertEqual(res_json["summary"]["total_input_records"], 2)

    def test_api_reset_database(self):
        response = self.client.post("/api/reset-database")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")

if __name__ == "__main__":
    unittest.main()

