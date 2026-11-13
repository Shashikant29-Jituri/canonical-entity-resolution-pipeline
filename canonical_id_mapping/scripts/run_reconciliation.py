import argparse
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import get_connection
from src.database.repository import CanonicalRepository

def generate_reconciliation_report(db_path: str, output_md_path: Optional[str] = None) -> Dict[str, Any]:
    conn = get_connection(db_path)
    cursor = conn.cursor()

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_path,
        "checks": {},
        "metrics": {}
    }

    # 1. Total counts across core tables
    tables = [
        "canonical_entities",
        "source_to_canonical_mapping",
        "canonical_mapping_history",
        "unresolved_mappings",
        "pipeline_runs"
    ]
    counts = {}
    for tbl in tables:
        cursor.execute(f"SELECT COUNT(*) AS total FROM {tbl}")
        counts[tbl] = cursor.fetchone()["total"]
    report["table_row_counts"] = counts

    # 2. Referential integrity: Orphan mappings
    cursor.execute("""
        SELECT COUNT(*) AS orphan_count
        FROM source_to_canonical_mapping m
        LEFT JOIN canonical_entities c ON m.canonical_id = c.canonical_id
        WHERE c.canonical_id IS NULL
    """)
    orphan_active = cursor.fetchone()["orphan_count"]

    cursor.execute("""
        SELECT COUNT(*) AS orphan_history
        FROM canonical_mapping_history h
        LEFT JOIN canonical_entities c ON h.canonical_id = c.canonical_id
        WHERE c.canonical_id IS NULL
    """)
    orphan_history = cursor.fetchone()["orphan_history"]

    report["checks"]["referential_integrity"] = {
        "passed": (orphan_active == 0 and orphan_history == 0),
        "orphan_active_mappings": orphan_active,
        "orphan_history_records": orphan_history
    }

    # 3. Active mapping uniqueness: Ensure exactly 1 active mapping per source key
    cursor.execute("""
        SELECT source_system, source_record_id, COUNT(*) AS active_count
        FROM source_to_canonical_mapping
        WHERE is_active = 1
        GROUP BY source_system, source_record_id
        HAVING COUNT(*) > 1
    """)
    duplicate_active = cursor.fetchall()
    report["checks"]["active_mapping_uniqueness"] = {
        "passed": (len(duplicate_active) == 0),
        "violations_count": len(duplicate_active)
    }

    # 4. SCD Type 2 Consistency: Ensure exactly 1 is_current=1 per source key in history
    cursor.execute("""
        SELECT source_system, source_record_id, COUNT(*) as current_count
        FROM canonical_mapping_history
        WHERE is_current = 1
        GROUP BY source_system, source_record_id
        HAVING COUNT(*) > 1
    """)
    scd_violations = cursor.fetchall()
    report["checks"]["scd2_interval_consistency"] = {
        "passed": (len(scd_violations) == 0),
        "violations_count": len(scd_violations)
    }

    # 5. Match type breakdown
    cursor.execute("""
        SELECT match_type, COUNT(*) as count
        FROM source_to_canonical_mapping
        WHERE is_active = 1
        GROUP BY match_type
        ORDER BY count DESC
    """)
    report["metrics"]["match_type_breakdown"] = [
        {"match_type": row["match_type"], "count": row["count"]}
        for row in cursor.fetchall()
    ]

    # 6. Unresolved / Quarantine breakdown
    cursor.execute("""
        SELECT reason_code, severity, COUNT(*) as count
        FROM unresolved_mappings
        GROUP BY reason_code, severity
        ORDER BY count DESC
    """)
    report["metrics"]["unresolved_breakdown"] = [
        {"reason_code": row["reason_code"], "severity": row["severity"], "count": row["count"]}
        for row in cursor.fetchall()
    ]

    # 7. Pipeline runs summary
    cursor.execute("""
        SELECT run_id, pipeline_name, start_time, duration_seconds, status,
               input_records_count, valid_records_count, mapped_existing_count,
               created_canonical_count, unresolved_count, rejected_count, duplicate_records_count
        FROM pipeline_runs
        ORDER BY start_time DESC
        LIMIT 10
    """)
    report["recent_pipeline_runs"] = [dict(row) for row in cursor.fetchall()]

    conn.close()

    # Generate Markdown Report
    md_content = f"""# Data Reconciliation & Integrity Audit Report

**Generated:** {report['timestamp']}  
**Database:** `{report['database']}`  

---

## 1. Automated Integrity Checks

| Check Name | Status | Details |
| :--- | :---: | :--- |
| **Referential Integrity** | {"✅ PASS" if report['checks']['referential_integrity']['passed'] else "❌ FAIL"} | Active orphans: {orphan_active}, History orphans: {orphan_history} |
| **Active Key Uniqueness** | {"✅ PASS" if report['checks']['active_mapping_uniqueness']['passed'] else "❌ FAIL"} | Duplicate active keys: {report['checks']['active_mapping_uniqueness']['violations_count']} |
| **SCD-2 Consistency** | {"✅ PASS" if report['checks']['scd2_interval_consistency']['passed'] else "❌ FAIL"} | Multi-current history violations: {report['checks']['scd2_interval_consistency']['violations_count']} |

---

## 2. Table Row Counts

| Table Name | Row Count |
| :--- | :---: |
| `canonical_entities` | {counts['canonical_entities']} |
| `source_to_canonical_mapping` | {counts['source_to_canonical_mapping']} |
| `canonical_mapping_history` | {counts['canonical_mapping_history']} |
| `unresolved_mappings` | {counts['unresolved_mappings']} |
| `pipeline_runs` | {counts['pipeline_runs']} |

---

## 3. Resolution & Match Distribution

| Match Type | Total Mappings |
| :--- | :---: |
"""
    for m in report["metrics"]["match_type_breakdown"]:
        md_content += f"| `{m['match_type']}` | {m['count']} |\n"

    md_content += """
---

## 4. Quarantined & Unresolved Mappings Breakdown

| Reason Code | Severity | Quarantined Count |
| :--- | :---: | :---: |
"""
    for u in report["metrics"]["unresolved_breakdown"]:
        md_content += f"| `{u['reason_code']}` | `{u['severity']}` | {u['count']} |\n"

    if output_md_path:
        out_p = Path(output_md_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(md_content)

    return report

def main():
    parser = argparse.ArgumentParser(description="Run reconciliation and audit checks against canonical database.")
    parser.add_argument("--db", type=str, default="data/canonical_store.db", help="Path to SQLite database")
    parser.add_argument("--report-out", type=str, default="data/output/reconciliation_report.md", help="Markdown report output path")

    args = parser.parse_args()
    report = generate_reconciliation_report(args.db, args.report_out)

    print("\n" + "=" * 65)
    print("RECONCILIATION & INTEGRITY AUDIT")
    print("=" * 65)
    print(f"Database: {args.db}")
    print(f"Referential Integrity: {'PASS' if report['checks']['referential_integrity']['passed'] else 'FAIL'}")
    print(f"Active Key Uniqueness: {'PASS' if report['checks']['active_mapping_uniqueness']['passed'] else 'FAIL'}")
    print(f"SCD-2 Consistency:     {'PASS' if report['checks']['scd2_interval_consistency']['passed'] else 'FAIL'}")
    print("-" * 65)
    print("Row Counts:")
    for k, v in report["table_row_counts"].items():
        print(f"  {k:30s}: {v}")
    print("=" * 65)
    if args.report_out:
        print(f"Detailed Markdown report saved to: {args.report_out}")

if __name__ == "__main__":
    main()
