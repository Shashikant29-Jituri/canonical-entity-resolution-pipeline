import argparse
import random
import json
import csv
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker"
]

SOURCE_SYSTEMS = [
    "crm_salesforce", "billing_stripe", "support_zendesk", "web_segment", "legacy_oracle"
]

DOMAINS = ["example.com", "company.org", "service.net", "platform.io", "enterprise.co"]

def generate_dataset(
    count: int = 1000,
    seed: int = 42,
    output_path: str = "data/synthetic_records.jsonl",
    file_format: str = "jsonl"
) -> Dict[str, Any]:
    """Generates synthetic dataset with realistic distribution, edge cases, conflicts, and nulls."""
    random.seed(seed)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    base_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    records = []
    
    # Pre-generate a pool of 200 known core entity seeds to simulate realistic cross-source linkages
    entity_pool = []
    for i in range(200):
        first = FIRST_NAMES[i % len(FIRST_NAMES)]
        last = LAST_NAMES[i % len(LAST_NAMES)]
        email = f"{first.lower()}.{last.lower()}.{i:03d}@{DOMAINS[i % len(DOMAINS)]}"
        phone = f"555{i:04d}"
        ssn = f"{800 + (i % 100):03d}-{(i * 7) % 100:02d}-{1000 + i:04d}"
        zip_code = f"{10000 + (i * 37) % 89999:05d}"
        entity_pool.append({
            "name": f"{first} {last}",
            "first": first,
            "last": last,
            "email": email,
            "phone": phone,
            "ssn": ssn,
            "zip": zip_code
        })

    conflict_count = 0
    malformed_count = 0
    duplicate_count = 0
    missing_key_count = 0

    for i in range(count):
        roll = random.random()
        src = random.choice(SOURCE_SYSTEMS)
        rec_id = f"REC_{i:07d}"
        # Event timestamp with jitter (some late-arriving / out-of-order)
        jitter_minutes = random.randint(-10000, 10000)
        event_time = (base_date + timedelta(minutes=i * 5 + jitter_minutes)).isoformat()

        # Scenario 1: Malformed Record (2%)
        if roll < 0.02:
            malformed_count += 1
            record = {
                "source_system": src,
                "source_record_id": rec_id,
                "email": "not-an-email-value",
                "date_of_birth": "32-13-1990",  # Illegal date
                "event_timestamp": "invalid-timestamp-string"
            }

        # Scenario 2: Missing Required Field (2%)
        elif roll < 0.04:
            missing_key_count += 1
            record = {
                "source_system": src,
                "source_record_id": "",  # Empty key
                "email": f"orphan_{i}@test.com",
                "first_name": "Ghost",
                "event_timestamp": event_time
            }

        # Scenario 3: Cross-Rule 1-to-Many Conflict (3%)
        elif roll < 0.07:
            conflict_count += 1
            # Pick two distinct entity seeds
            e1 = entity_pool[i % len(entity_pool)]
            e2 = entity_pool[(i + 47) % len(entity_pool)]
            record = {
                "source_system": src,
                "source_record_id": rec_id,
                "email": e1["email"],   # points to Entity 1
                "phone": e2["phone"],   # points to Entity 2
                "first_name": e1["first"],
                "last_name": e2["last"],
                "postal_code": e1["zip"],
                "country": "US",
                "event_timestamp": event_time
            }

        # Scenario 4: Exact Intra-batch Duplicate (5%)
        elif roll < 0.12 and i > 10:
            duplicate_count += 1
            # Duplicate a previously generated valid record
            prev_e = entity_pool[(i - 5) % len(entity_pool)]
            record = {
                "source_system": src,
                "source_record_id": f"REC_{i - 5:07d}",
                "email": prev_e["email"],
                "phone": prev_e["phone"],
                "first_name": prev_e["first"],
                "last_name": prev_e["last"],
                "postal_code": prev_e["zip"],
                "country": "US",
                "event_timestamp": event_time
            }

        # Scenario 5: Linked Record Matching Seed Pool (~40%)
        elif roll < 0.52:
            e = entity_pool[i % len(entity_pool)]
            record = {
                "source_system": src,
                "source_record_id": rec_id,
                "email": e["email"],
                "phone": e["phone"] if random.random() > 0.2 else None,
                "national_id": e["ssn"] if random.random() > 0.4 else None,
                "first_name": e["first"],
                "last_name": e["last"],
                "postal_code": e["zip"],
                "country": "US",
                "event_timestamp": event_time
            }

        # Scenario 6: Novel Valid Entity Creation (~48%)
        else:
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            record = {
                "source_system": src,
                "source_record_id": rec_id,
                "email": f"{fn.lower()}.{ln.lower()}.novel{i}@{random.choice(DOMAINS)}",
                "phone": f"555{random.randint(1000000, 9999999)}",
                "first_name": fn,
                "last_name": ln,
                "postal_code": f"{random.randint(10000, 99999)}",
                "country": "US",
                "event_timestamp": event_time
            }

        records.append(record)

    # Write output
    if file_format == "jsonl":
        with open(output_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
    elif file_format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    elif file_format == "csv":
        fieldnames = [
            "source_system", "source_record_id", "national_id", "email",
            "phone", "first_name", "last_name", "legal_name", "date_of_birth",
            "postal_code", "country", "event_timestamp"
        ]
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in records:
                writer.writerow(r)

    stats = {
        "total_records": count,
        "seed": seed,
        "output_path": output_path,
        "format": file_format,
        "conflict_records": conflict_count,
        "malformed_records": malformed_count,
        "duplicate_records": duplicate_count,
        "missing_key_records": missing_key_count
    }
    return stats

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic data for Canonical ID Mapping pipeline.")
    parser.add_argument("--count", type=int, default=1000, help="Number of records to generate")
    parser.add_argument("--seed", type=int, default=42, help="Fixed random seed")
    parser.add_argument("--output", type=str, default="data/sample/generated_records.jsonl", help="Output file path")
    parser.add_argument("--format", type=str, choices=["jsonl", "json", "csv"], default="jsonl", help="File format")

    args = parser.parse_args()
    summary = generate_dataset(
        count=args.count,
        seed=args.seed,
        output_path=args.output,
        file_format=args.format
    )
    print(json.dumps(summary, indent=2))
