"""
Master All-in-One Execution Script for Canonical ID Mapping Pipeline
Runs the entire workflow end-to-end:
1. Automated Test Suite (22 tests)
2. Sample Pipeline Execution & Ingestion
3. Data Reconciliation & Integrity Audit
4. Result Inspection (Active Mappings & Quarantined Conflicts)
5. Performance Benchmark (10,000 records)
"""
import sys
import os
import subprocess
import time
from pathlib import Path

def print_header(title: str):
    print("\n" + "=" * 80)
    print(f" {title.upper()}")
    print("=" * 80)

def run_step(step_num: int, title: str, cmd: list):
    print_header(f"Step {step_num}: {title}")
    print(f"Executing: {' '.join(cmd)}\n")
    t0 = time.time()
    result = subprocess.run([sys.executable] + cmd, capture_output=False)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"\n[ERROR] Step {step_num} failed with return code {result.returncode}")
        sys.exit(result.returncode)
    print(f"\n[OK] Step {step_num} completed successfully in {elapsed:.2f}s")

def main():
    print_header("CANONICAL ID MAPPING & ENTITY RESOLUTION PIPELINE - ALL-IN-ONE RUNNER")

    # Step 1: Run automated test suite
    run_step(1, "Run Automated Test Suite (22 Tests)", ["-m", "unittest", "discover", "tests"])

    # Step 2: Run pipeline on sample data
    db_path = "data/canonical_store.db"
    # Ensure fresh DB for demonstration
    for suffix in ["", "-wal", "-shm"]:
        p = Path(f"{db_path}{suffix}")
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    run_step(2, "Execute Canonical Pipeline on Sample Feed", [
        "scripts/run_pipeline.py",
        "--input", "data/sample/source_records_sample.json",
        "--seed-canonical", "data/sample/seed_canonical_entities.json",
        "--db", db_path
    ])

    # Step 3: Run reconciliation audit
    run_step(3, "Execute Reconciliation & Data Quality Audit", [
        "scripts/run_reconciliation.py",
        "--db", db_path,
        "--report-out", "data/output/reconciliation_report.md"
    ])

    # Step 4: Display database inspection tables
    run_step(4, "Inspect Active Mappings, Conflicts & Entities", ["scripts/inspect_results.py"])

    # Step 5: Run performance benchmark (10,000 records)
    run_step(5, "Execute Performance Benchmark (10,000 records)", [
        "scripts/benchmark_performance.py",
        "--count", "10000",
        "--batch-size", "5000"
    ])

    print_header("ALL PIPELINE STEPS COMPLETED SUCCESSFULLY!")
    print("Summary of outputs generated:")
    print(f"  - Database:               {db_path}")
    print("  - Reconciliation Report:  data/output/reconciliation_report.md")
    print("  - Benchmark Metrics:      data/output/benchmark_results.json")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()

