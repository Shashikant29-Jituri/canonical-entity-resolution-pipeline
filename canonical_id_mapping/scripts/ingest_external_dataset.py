"""
Generic External Dataset Ingestion Adapter for Entity Resolution
Supports mapping arbitrary external CSV / JSON entity resolution datasets
(e.g., Table A / Table B, Febrl, Dedupe, Kaggle customer datasets)
into the Canonical ID Mapping Pipeline.
"""

import argparse
import sys
import csv
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import init_db
from src.pipeline.runner import execute_pipeline
from src.utils.logger import get_logger

logger = get_logger("external_ingest")

def convert_external_dataset(
    input_file: str,
    output_jsonl: str,
    source_system: str = "external_source",
    id_col: Optional[str] = None,
    email_col: Optional[str] = None,
    phone_col: Optional[str] = None,
    name_col: Optional[str] = None,
    first_name_col: Optional[str] = None,
    last_name_col: Optional[str] = None,
    zip_col: Optional[str] = None,
    ssn_col: Optional[str] = None,
    dob_col: Optional[str] = None,
    country_col: Optional[str] = None,
    timestamp_col: Optional[str] = None
) -> int:
    """Reads any external CSV or JSON file, detects or maps fields, and formats as canonical JSONL."""
    in_path = Path(input_file)
    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    rows: List[Dict[str, Any]] = []
    ext = in_path.suffix.lower()

    if ext == ".csv":
        with open(in_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            # Auto-detect column names if not explicitly specified
            header = reader.fieldnames or []
            h_map = {h.lower().replace(" ", "_"): h for h in header}

            # Helper to find column matching aliases
            def find_col(explicit: Optional[str], aliases: List[str]) -> Optional[str]:
                if explicit and explicit in header:
                    return explicit
                for a in aliases:
                    if a in h_map:
                        return h_map[a]
                return None

            c_id = id_col or find_col(None, ["id", "record_id", "customer_id", "user_id", "entity_id", "client_id", "account_id", "patient_id", "ticket_id", "order_id", "product_id", "item_id", "emp_id", "member_id", "pk", "uuid", "key"])
            c_email = email_col or find_col(None, ["email", "mail", "primary_email", "email_address", "contact_email", "user_email"])
            c_phone = phone_col or find_col(None, ["phone", "telephone", "mobile", "phone_number", "contact_no", "contact_phone", "cell", "tel"])
            c_name = name_col or find_col(None, ["name", "full_name", "legal_name", "customer_name", "client_name", "user_name", "contact_name", "patient_name", "account_name", "title", "product_name", "item_name", "entity_name", "label", "description", "headline"])
            c_first = first_name_col or find_col(None, ["first_name", "given_name", "fname", "firstname"])
            c_last = last_name_col or find_col(None, ["last_name", "surname", "lname", "lastname"])
            c_zip = zip_col or find_col(None, ["zip", "postal_code", "zip_code", "postcode", "zipcode", "category", "brand", "dept"])
            c_ssn = ssn_col or find_col(None, ["ssn", "national_id", "tax_id", "nin", "gov_id", "ein", "modelno", "model_no", "model_number", "sku", "upc", "asin", "isbn", "code", "part_number", "partno"])
            c_dob = dob_col or find_col(None, ["dob", "date_of_birth", "birthdate", "birthday"])
            c_country = country_col or find_col(None, ["country", "country_code", "nation"])
            c_ts = timestamp_col or find_col(None, ["timestamp", "created_at", "updated_at", "event_time", "date"])

            for idx, r in enumerate(reader):
                rec_id = r.get(c_id) if c_id else f"ROW_{idx:05d}"
                if not rec_id:
                    rec_id = f"ROW_{idx:05d}"

                clean_record = {
                    "source_system": source_system,
                    "source_record_id": str(rec_id).strip(),
                    "email": r.get(c_email) if c_email else None,
                    "phone": r.get(c_phone) if c_phone else None,
                    "legal_name": r.get(c_name) if c_name else None,
                    "first_name": r.get(c_first) if c_first else None,
                    "last_name": r.get(c_last) if c_last else None,
                    "postal_code": r.get(c_zip) if c_zip else None,
                    "national_id": r.get(c_ssn) if c_ssn else None,
                    "date_of_birth": r.get(c_dob) if c_dob else None,
                    "country": r.get(c_country) if c_country else "US",
                    "event_timestamp": r.get(c_ts) if c_ts else datetime.now(timezone.utc).isoformat(),
                    "attributes": {k: v for k, v in r.items() if v}
                }
                rows.append(clean_record)

    elif ext in (".json", ".jsonl"):
        with open(in_path, "r", encoding="utf-8") as f:
            if ext == ".json":
                content = json.load(f)
                if isinstance(content, dict):
                    content = [content]
            else:
                content = [json.loads(line) for line in f if line.strip()]

        for idx, r in enumerate(content):
            rec_id = r.get("source_record_id") or r.get("id") or r.get("customer_id") or f"ROW_{idx:05d}"
            clean_record = {
                "source_system": r.get("source_system", source_system),
                "source_record_id": str(rec_id).strip(),
                "email": r.get("email") or r.get("mail"),
                "phone": r.get("phone") or r.get("mobile"),
                "legal_name": r.get("legal_name") or r.get("name") or r.get("full_name") or r.get("title") or r.get("product_name"),
                "first_name": r.get("first_name"),
                "last_name": r.get("last_name"),
                "postal_code": r.get("postal_code") or r.get("zip") or r.get("category") or r.get("brand"),
                "national_id": r.get("national_id") or r.get("ssn") or r.get("modelno") or r.get("sku") or r.get("tax_id"),
                "date_of_birth": r.get("date_of_birth") or r.get("dob"),
                "country": r.get("country", "US"),
                "event_timestamp": r.get("event_timestamp") or datetime.now(timezone.utc).isoformat(),
                "attributes": r.get("attributes", {})
            }
            rows.append(clean_record)

    # Write normalized JSONL
    out_p = Path(output_jsonl)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    logger.info(f"Adapted {len(rows)} records from {input_file} into {output_jsonl}")
    return len(rows)

def main():
    parser = argparse.ArgumentParser(description="Ingest external Entity Resolution datasets into Canonical Pipeline.")
    parser.add_argument("--input", type=str, required=True, help="Path to external CSV or JSON file")
    parser.add_argument("--source-system", type=str, default="external_feed", help="Name of source system")
    parser.add_argument("--db", type=str, default="data/canonical_store.db", help="Target SQLite DB path")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch chunk size")

    args = parser.parse_args()

    intermediate_jsonl = f"data/converted_{args.source_system}.jsonl"
    count = convert_external_dataset(
        input_file=args.input,
        output_jsonl=intermediate_jsonl,
        source_system=args.source_system
    )

    print(f"[OK] Converted {count:,} external records. Running Canonical Resolution Pipeline...")
    metrics = execute_pipeline(
        input_file=intermediate_jsonl,
        db_path=args.db,
        batch_size=args.batch_size,
        auto_create_canonical=True
    )

    print("\n" + "=" * 65)
    print("EXTERNAL DATASET RESOLUTION SUMMARY")
    print("=" * 65)
    print(metrics.to_json())
    print("=" * 65)
    print(f"\nView the results live in your web browser: http://localhost:5000")

if __name__ == "__main__":
    main()

