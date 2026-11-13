import unittest
from src.matching.normalizers import (
    normalize_email,
    normalize_phone,
    normalize_name,
    normalize_national_id,
    normalize_postal_code,
    build_normalized_record
)

class TestNormalizers(unittest.TestCase):
    def test_email_normalization(self):
        self.assertEqual(normalize_email("  User.Name+Tag@Example.COM "), "user.name+tag@example.com")
        self.assertIsNone(normalize_email("not-an-email"))
        self.assertIsNone(normalize_email(""))
        self.assertIsNone(normalize_email(None))

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("+1 (555) 123-4567"), "5551234567")
        self.assertEqual(normalize_phone("1-555-987-6543"), "5559876543")
        self.assertEqual(normalize_phone("555.888.9999"), "5558889999")
        self.assertIsNone(normalize_phone("123"))  # Too short
        self.assertIsNone(normalize_phone(None))

    def test_name_normalization(self):
        norm, raw = normalize_name(first_name="Jane", last_name="Doe")
        self.assertEqual(norm, "jane doe")
        self.assertEqual(raw, "Jane Doe")

        norm_corp, _ = normalize_name(legal_name="Acme Technology, Inc.")
        self.assertEqual(norm_corp, "acme technology")

        norm_llc, _ = normalize_name(legal_name="Global Logistics LLC")
        self.assertEqual(norm_llc, "global logistics")

    def test_national_id_normalization(self):
        self.assertEqual(normalize_national_id("999-11-2222"), "999112222")
        self.assertEqual(normalize_national_id(" tax_99182  "), "TAX99182")
        self.assertIsNone(normalize_national_id(None))

    def test_postal_code_normalization(self):
        self.assertEqual(normalize_postal_code("94101-1234"), "94101")
        self.assertEqual(normalize_postal_code("  94101 "), "94101")
        self.assertEqual(normalize_postal_code("sw1a 1aa"), "SW1A 1AA")
        self.assertIsNone(normalize_postal_code(None))

if __name__ == "__main__":
    unittest.main()

