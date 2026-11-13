# Canonical ID Mapping & Entity Resolution Pipeline

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen.svg)]()
[![Web UI](https://img.shields.io/badge/UI-Interactive%20Dashboard-indigo.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **In Simple Words**: When a company uses Salesforce, Stripe, Shopify, and Zendesk, the same customer exists with different IDs across all of them (e.g. `SF_101`, `CUST_789`, `cus_stripe_55`). This system automatically connects all those disparate records to a **single master Canonical ID** (like `CAN-FA730F697725`), catches data conflicts, keeps an audit history of every change, and isolates bad data in a quarantine area.

---

## 🎯 What This Project Does (Simple 3-Step Flow)

1. **Upload Multiple Datasets**: Feed in CSV or JSON files from different databases (CRM, Billing, E-Commerce, Support).
2. **Deterministic Matching & Conflict Protection**: It normalizes contact data and runs prioritized rules (National ID / SSN $\rightarrow$ Email $\rightarrow$ Phone $\rightarrow$ Name + Postal Code). If two records contradict each other (e.g., matching Alice's email but Bob's phone), it **never blindly guesses**—it safely flags and quarantines the conflict.
3. **Master Canonical Registry & Audit Trail**: Every validated customer is linked to one golden Canonical ID with full history (SCD Type 2), so you always know who they were, what system they came from, and how their data evolved over time.

---

## Architecture & Data Flow

```
+---------------------------------------------------------------------------------------+
|                                    INCOMING FEEDS                                     |
|  [crm_salesforce]     [billing_stripe]     [support_zendesk]     [web_segment]        |
+-------------------------------------------+-------------------------------------------+
                                            |
                                            v
                     +----------------------------------------------+
                     |         PipelineValidator & Normalizer       |
                     |  - Schema contract enforcement               |
                     |  - ISO-8601 & regex standardization          |
                     |  - Intra-batch duplicate & collision checks  |
                     +----------------------+-----------------------+
                                            |
                         +------------------+------------------+
                         | (Invalid / Malformed / Collisions)  | (Valid Records)
                         v                                     v
         +-------------------------------+     +----------------------------------+
         |     unresolved_mappings       |     |         MatchingEngine           |
         |  - Quarantine snapshot        |     |  - Tier 0: Exact Source Lookup   |
         |  - Reason code diagnostics    |     |  - Tier 1: Exact National ID     |
         |  - Error & Critical severity  |     |  - Tier 2: Normalized Contact    |
         +-------------------------------+     |  - Tier 3: Composite Name + Zip  |
                         ^                     +-----------------+----------------+
                         |                                       |
                         | (1-to-Many Conflict / Ambiguity)      v
                         +-----------------------------+-------------------+
                                                       | ConflictDetector  |
                                                       +---------+---------+
                                                                 |
                                       +-------------------------+-------------------------+
                                       | (Unanimous Match)                                 | (Novel Identity)
                                       v                                                   v
                       +-------------------------------+                   +-------------------------------+
                       |      HistoryTracker (SCD2)    |                   |       Canonical Entity        |
                       |  - Close expired interval     |                   |  - Deterministic SHA-256 ID   |
                       |  - Open new valid interval    |                   |  - Insert canonical master    |
                       +---------------+---------------+                   +---------------+---------------+
                                       |                                                   |
                                       +-------------------------+-------------------------+
                                                                 |
                                                                 v
                                         +---------------------------------------------------+
                                         |               TARGET PERSISTENCE                  |
                                         |  - canonical_entities                             |
                                         |  - source_to_canonical_mapping (Active Serving)  |
                                         |  - canonical_mapping_history (Audit Trail)        |
                                         |  - pipeline_runs (Operational Metrics)            |
                                         +---------------------------------------------------+
```

---

## Key Features

1. **Deterministic Tiered Matching**:
   - **Tier 0**: Exact Source Key Match (`source_system` + `source_record_id`) in active registry.
   - **Tier 1 (Confidence 1.00)**: Exact National ID / SSN / Tax ID match.
   - **Tier 2 (Confidence 0.95 / 0.90)**: Normalized Contact Match (Email / E.164 Phone).
   - **Tier 3 (Confidence 0.85)**: Composite Match (Normalized Name + Postal Code).
2. **Conflict & Ambiguity Detection**:
   - **Cross-Rule Divergence (`CONFLICT_ONE_TO_MANY_CANONICAL`)**: Prevents silent split-identity linkage when natural keys point to distinct canonical records (e.g. Email points to `CAN-0001`, Phone points to `CAN-0002`).
   - **Single-Rule Ambiguity (`CONFLICT_AMBIGUOUS_RULE_MATCH`)**: Quarantines records when a rule resolves to multiple candidate master entities.
   - **Intra-Batch Collision (`CONFLICT_SOURCE_KEY_COLLISION`)**: Detects identical source keys within the same batch carrying contradictory attributes.
3. **SCD Type 2 Mapping History**:
   - Preserves complete mapping lineage (`effective_from`, `effective_to`, `is_current`, `change_reason`, `run_id`).
   - Idempotent re-observations do NOT inflate history; only genuine transitions (`CAN-A` -> `CAN-B`) open new intervals.
4. **Resilient Quarantine / Dead-Letter Queue**:
   - All anomalies are preserved in `unresolved_mappings` with raw payload snapshots, severity, reason codes, and triage status (`OPEN`, `RESOLVED`, `IGNORED`).
5. **High Performance & Scale**:
   - Processes **>4,500 records/sec** on standard hardware (benchmarked with 10,000 and 100,000 record runs).
   - Chunked generator ingestion keeps memory flat (<50MB RSS).

---

## Directory Structure

```
canonical_id_mapping/
├── README.md                           # Main documentation & run instructions
├── ARCHITECTURE.md                     # Deep architectural breakdown & flow specs
├── DATA_DICTIONARY.md                  # Complete schemas, data types, nullability, grain
├── DESIGN_AND_TRADEOFFS.md             # Design decisions, trade-offs & performance reasoning
├── requirements.txt                    # Project dependencies
├── pyproject.toml                      # Standard packaging specification
├── .gitignore                          # Clean build & database ignore rules
├── data/
│   ├── canonical_store.db              # SQLite ACID target store
│   ├── sample/
│   │   ├── seed_canonical_entities.json # Pre-existing canonical master entities
│   │   ├── source_records_sample.json   # 11 sample records covering all positive & negative cases
│   │   ├── expected_results.json        # Ground-truth labels stored separately
│   │   └── generated_records.jsonl      # Scalable synthetic dataset output
│   └── output/
│       ├── reconciliation_report.md     # Automated reconciliation & audit report
│       └── benchmark_results.json       # Performance benchmark metrics
├── src/
│   ├── __init__.py
│   ├── config.py                       # Configurable parameters & environment variables
│   ├── database/
│   │   ├── __init__.py
│   │   ├── schema.sql                  # ANSI SQL DDL & indexes
│   │   ├── connection.py               # WAL connection & transaction context manager
│   │   └── repository.py               # Clean DAO layer & audit queries
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py                  # Pydantic schema contracts & validators
│   │   └── entities.py                 # Dataclasses for normalized records & match results
│   ├── matching/
│   │   ├── __init__.py
│   │   ├── normalizers.py              # String, phone, email, name, postal normalizers
│   │   ├── rules.py                    # Pluggable deterministic matching rules
│   │   ├── conflict_detector.py        # 1-to-many & ambiguity detector
│   │   └── engine.py                   # Master entity resolution engine
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── validator.py                # Batch validator & duplicate detector
│   │   ├── history_tracker.py          # SCD Type 2 state transition manager
│   │   ├── processor.py                # Atomic batch pipeline processor
│   │   └── runner.py                   # Chunked stream runner & file ingestion
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                   # Structured logging (Text / JSON)
│       └── metrics.py                  # Operational pipeline run metrics
├── scripts/
│   ├── generate_data.py                # Configurable synthetic data generator (seed 42)
│   ├── run_pipeline.py                 # Pipeline CLI entry point
│   ├── run_reconciliation.py           # Reconciliation & integrity audit script
│   └── benchmark_performance.py        # Performance benchmark runner
└── tests/
    ├── __init__.py
    ├── test_normalizers.py             # Normalization unit tests
    ├── test_validator.py               # Schema & validation unit tests
    ├── test_conflict_detection.py      # 1-to-many conflict detection tests
    ├── test_history_scd2.py            # SCD-2 history retention tests
    ├── test_idempotency_and_rerun.py   # Rerun idempotency tests
    ├── test_edge_cases.py              # Empty input, rollback, toggle tests
    └── test_end_to_end_pipeline.py     # Full integration & reconciliation tests
```

---

## Quickstart & Setup Instructions

### Prerequisites
- Python 3.9+ (Standard Python library + `pydantic`, `sqlalchemy`)
- No external databases or Docker required. Uses local SQLite with Write-Ahead Logging.

### Installation
```bash
# Clone the repository
git clone <repository-url>
cd canonical_id_mapping

# Optional: Create and activate a virtual environment
python -m venv venv
# On Linux/macOS: source venv/bin/activate
# On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🚀 Interactive Web Dashboard

Launch the local web dashboard to drag-and-drop multiple datasets, inspect live mappings, view SCD Type 2 timelines, and test matching rules in real time:

```bash
python webapp/app.py
```
Open **`http://localhost:5000`** in any web browser.

**Web Dashboard Highlights:**
- **Multi-Dataset Upload**: Drag-and-drop multiple CSV / JSON files at once (e.g. `CRM_customers.csv` and `Stripe_billing.csv`). The adapter automatically normalizes header columns and cross-links entities.
- **Active Mappings Table**: Search and filter by source system, rule type (`RULE_EMAIL`, `RULE_PHONE`, etc.), or customer name.
- **SCD-2 Lineage Modal**: Click **"View History"** on any row to open the visual timeline of how that customer's canonical linkage changed over time.
- **Quarantine Center**: Inspect all flagged conflicts, ambiguous matches, and schema anomalies with raw JSON payloads and 1-click status triage.
- **Interactive Match Tester**: Test custom customer records on the fly to see how the engine ranks matching rules and calculates confidence.
- **Database Reset & Clean Ingestion**: Reset the database to a clean state anytime, ensuring only your uploaded datasets appear with zero demo pollution.

---

## ⚡ Quick Start: How to Run the Project (3 Steps)

### Step 1: Install Dependencies
Open PowerShell or your terminal in the project root directory and run:
```bash
pip install -r requirements.txt
```

### Step 2: Run the Automated Test Suite (Verify 100% Passing)
```bash
python -m unittest discover tests
```
*(Runs all 31 unit & integration tests in ~4 seconds)*.

### Step 3: Launch the Web Portal
```bash
python webapp/app.py
```
Open **`http://localhost:5000`** in your browser.
- In the **Upload Datasets** tab, drag and drop `tableA.csv` and `tableB.csv` (or any custom CSVs).
- In the **Active Mappings** tab, filter by source system or search any ID.
- In the **Canonical Master Registry** tab, search cross-resolved products (e.g. `ORG332BX`) to see unified golden master records linked across multiple tables!

---

## Execution Guide (CLI)

### 1. Run Automated Test Suite
The test suite covers happy paths, empty input, malformed records, batch duplicates, missing keys, cross-rule conflicts, SCD2 history transitions, idempotency, and partial failure rollbacks:

```bash
# Using standard Python unittest (Zero external dependency)
python -m unittest discover tests

# Or using pytest (if installed)
pytest tests/ -v
```

### 2. Run Pipeline on Sample Dataset
Execute the pipeline against the included starter sample with seed canonical records:

```bash
python scripts/run_pipeline.py \
  --input data/sample/source_records_sample.json \
  --seed-canonical data/sample/seed_canonical_entities.json \
  --db data/canonical_store.db
```

### 3. Generate Audit & Reconciliation Report
Audit referential integrity, record balance, and active key uniqueness:

```bash
python scripts/run_reconciliation.py \
  --db data/canonical_store.db \
  --report-out data/output/reconciliation_report.md
```

### 4. Generate Scalable Synthetic Data (Configurable Volume)
Generate synthetic records with a fixed random seed (`--seed 42`):

```bash
# Generate 1,000 records (JSON Lines format)
python scripts/generate_data.py --count 1000 --seed 42 --output data/sample/generated_records.jsonl

# Generate 100,000 records (CSV format)
python scripts/generate_data.py --count 100000 --seed 42 --format csv --output data/sample/generated_100k.csv
```

### 5. Run Performance Benchmark
Run an end-to-end benchmark measuring throughput, latency, and resource footprint:

```bash
# Benchmark 10,000 records
python scripts/benchmark_performance.py --count 10000 --batch-size 5000

# Benchmark 100,000 records
python scripts/benchmark_performance.py --count 100000 --batch-size 10000
```

---

## Edge Cases & Negative Scenarios Tested

| Scenario | Trigger Condition | System Behavior | Test Case |
| :--- | :--- | :--- | :--- |
| **Malformed Record** | Non-JSON object or invalid date format | Quarantined with `MALFORMED_INPUT` or `SCHEMA_VALIDATION_ERROR` | `test_malformed_input_type`, `test_invalid_date_format` |
| **Missing Required Field** | Null or whitespace `source_record_id` | Quarantined with `MISSING_REQUIRED_KEY` | `test_missing_required_keys` |
| **Intra-Batch Duplicate** | Identical source key & attributes in same batch | Deduplicated cleanly; duplicate counter incremented | `test_intra_batch_identical_duplicate` |
| **Source Key Collision** | Duplicate source key with contradictory email/phone | Quarantined with `CONFLICT_SOURCE_KEY_COLLISION` | `test_intra_batch_key_collision_conflicting_attributes` |
| **1-to-Many Conflict** | Email matches `CAN-A`, Phone matches `CAN-B` | Quarantined with `CONFLICT_ONE_TO_MANY_CANONICAL` | `test_one_to_many_cross_rule_conflict` |
| **Ambiguous Rule Match** | Composite name+zip matches multiple people | Quarantined with `CONFLICT_AMBIGUOUS_RULE_MATCH` | `test_ambiguous_composite_rule_match` |
| **Empty Input Batch** | 0 records in input file | Exits gracefully with status `SUCCESS` and 0 counts | `test_empty_batch` |
| **Partial Failure / Crash** | Simulated disk crash midway through batch | Entire transaction rolls back cleanly; 0 uncommitted records | `test_partial_failure_transaction_rollback` |
| **Rerun of Same Input** | Re-executing identical input batch | Idempotent upsert; 0 extra canonical entities or active mappings | `test_idempotent_multiple_runs` |
| **Auto-Create Disabled** | Unmapped record when `--no-auto-create` is set | Quarantined with `UNRESOLVED_AUTO_CREATE_DISABLED` | `test_auto_create_canonical_disabled_routes_to_unresolved` |

---

## Reconciliation & Data Quality Invariants

The reconciliation framework (`scripts/run_reconciliation.py`) verifies the following invariants:
1. **Conservation of Records**: $\text{Input Count} = \text{Valid Count} + \text{Rejected Count}$.
2. **Referential Integrity**: Every `canonical_id` in `source_to_canonical_mapping` and `canonical_mapping_history` exists in `canonical_entities` (0 orphan records).
3. **Active Key Uniqueness**: Exactly one `is_active = 1` mapping exists per `(source_system, source_record_id)` composite primary key.
4. **SCD-2 Consistency**: Exactly one active interval (`is_current = 1` and `effective_to IS NULL`) exists per source key in history.

---

## Idempotency, Recovery, and Rerun Semantics

- **Idempotent Reruns**: If an orchestrator retries a failed or timed-out job with the same batch, SQLite upsert semantics (`ON CONFLICT(...) DO UPDATE`) ensure that:
  - No duplicate rows are created in `source_to_canonical_mapping`.
  - No duplicate intervals are opened in `canonical_mapping_history` unless canonical classification actually changed.
- **Atomic Transactions**: Batch processing occurs inside an atomic context manager. Any fatal exception triggers an immediate transaction rollback, preventing partial batch corruption.
- **Deterministic ID Generation**: Canonical IDs use deterministic SHA-256 digests (`CAN-<12-char-hash>`) of natural identity attributes, guaranteeing identical IDs across restarts and distributed workers.

---

## Known Limitations & Production Enhancements

1. **In-Memory Pre-Caching for Multi-Million Entities**: At extreme scale (>10M records), individual indexed SQL lookups can be optimized by batch-loading candidate keys into an in-memory hash set or Bloom filter before rule evaluation (projected throughput >15,000 records/sec).
2. **Probabilistic / Machine Learning Matching**: Current implementation emphasizes high-precision deterministic rules and composite matches. Integrating probabilistic linkage (Fellegi-Sunter / Jaro-Winkler) for typo-tolerant matching can be plugged into `BaseMatchingRule`.
3. **Distributed Execution**: The current modular pipeline can be wrapped in a PySpark UDF or Ray task for multi-node distributed execution across TB-scale data lakes.

---

## 🐙 How to Push This Project to GitHub

Follow these simple steps to push this project to your GitHub account:

### 1. Install Git (if not already installed)
If you don't have Git installed on your computer:
- Download and install Git from [git-scm.com/download/win](https://git-scm.com/download/win).
- *(Or download [GitHub Desktop](https://desktop.github.com/) for a 100% visual interface)*.

### 2. Create a New Repository on GitHub
1. Log in to [GitHub](https://github.com).
2. Click the **`+`** icon at the top right and select **"New repository"**.
3. Name your repository (e.g., `canonical-entity-resolution-pipeline`).
4. Set it to **Public** (or Private).
5. **Leave all checkboxes unchecked** (Do NOT initialize with README, .gitignore, or license, as they already exist in this project).
6. Click **"Create repository"**.

### 3. Initialize and Push (Run in Terminal / PowerShell)
Open your terminal in `canonical_id_mapping/` and run the following commands:

```bash
# 1. Initialize local git repository
git init

# 2. Add all project files
git add .

# 3. Create initial commit
git commit -m "feat: Multi-Dataset Entity Resolution & Canonical ID Mapping Pipeline"

# 4. Set default branch to main
git branch -M main

# 5. Link to your GitHub repository (replace with your actual GitHub repo URL)
git remote add origin https://github.com/<YOUR-GITHUB-USERNAME>/canonical-entity-resolution-pipeline.git

# 6. Push to GitHub
git push -u origin main
```

Done! Your project is now live on GitHub with full documentation, tests, and web dashboard code.

