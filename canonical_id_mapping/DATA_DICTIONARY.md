# Data Dictionary & Schema Specification

## 1. Overview & Grain
The Canonical ID Mapping solution establishes a single deterministic master identity across disparate operational source systems (CRMs, Billing engines, Customer Support ticketing, Web Analytics, and Legacy DBs).

- **Source Grain**: One record per source event or entity extraction snapshot (`source_system` + `source_record_id`).
- **Target Serving Grain**: One row per distinct source identifier (`source_system` + `source_record_id`) mapping to its currently active `canonical_id`.
- **Target Master Grain**: One row per unique canonical entity (`canonical_id`).
- **History Grain (SCD-2)**: One row per mapping state interval per source identifier (`source_system` + `source_record_id` + `effective_from`).
- **Quarantine Grain**: One row per rejected or unresolved exception event.

---

## 2. Ingestion / Source Schema Contract (`SourceRecordSchema`)

| Field Name | Data Type | Nullable | Primary Key | Description & Validation Rules |
| :--- | :--- | :---: | :---: | :--- |
| `source_system` | `VARCHAR(64)` | No | Yes (Composite) | Originating system identifier (e.g. `crm_salesforce`, `billing_stripe`). Cannot be blank. |
| `source_record_id` | `VARCHAR(128)` | No | Yes (Composite) | Primary identifier in the source system. Cannot be empty or whitespace. |
| `national_id` | `VARCHAR(64)` | Yes | No | Government or tax identifier (e.g. SSN, EIN). Stripped of punctuation and uppercased. |
| `email` | `VARCHAR(255)` | Yes | No | Contact email. Validated via regex, trimmed, and converted to lowercase. |
| `phone` | `VARCHAR(32)` | Yes | No | Phone number. Non-numeric characters stripped; leading US country code handled. |
| `first_name` | `VARCHAR(100)` | Yes | No | Given name. Used in composite matching. |
| `last_name` | `VARCHAR(100)` | Yes | No | Family/surname. Used in composite matching. |
| `legal_name` | `VARCHAR(255)` | Yes | No | Full personal or legal business name. Stripped of business affixes (`Inc`, `LLC`, `Corp`). |
| `date_of_birth` | `VARCHAR(10)` | Yes | No | Date of birth. Enforced format: `YYYY-MM-DD`. |
| `postal_code` | `VARCHAR(20)` | Yes | No | ZIP or postal code. Standardized to 5 digits for US ZIP+4. |
| `country` | `VARCHAR(3)` | Yes | No | ISO country code (e.g. `US`, `CA`). |
| `event_timestamp` | `VARCHAR(35)` | Yes | No | Extraction or event timestamp in ISO-8601 format (`YYYY-MM-DDTHH:MM:SSZ`). |
| `attributes` | `JSON` | Yes | No | Arbitrary custom metadata dictionary for source-specific payloads. |

---

## 3. Storage Layer Schemas

### 3.1. `canonical_entities` (Master Entity Registry)
Stores resolved canonical entity profiles.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `canonical_id` | `TEXT` | `PRIMARY KEY` | Stable deterministic canonical ID (e.g. `CAN-A1B2C3D4E5F6`). |
| `primary_name` | `TEXT` | Nullable | Golden display name derived during entity resolution. |
| `primary_email` | `TEXT` | Nullable, Indexed | Normalized golden email address. |
| `primary_phone` | `TEXT` | Nullable, Indexed | Normalized golden phone digits. |
| `national_id` | `TEXT` | Nullable, Indexed | Normalized unique government/tax ID. |
| `postal_code` | `TEXT` | Nullable | Primary postal/ZIP code. |
| `country` | `TEXT` | Nullable | Primary country code. |
| `created_at` | `TEXT` | `NOT NULL` | ISO-8601 timestamp of entity creation. |
| `updated_at` | `TEXT` | `NOT NULL` | ISO-8601 timestamp of most recent entity update. |
| `entity_version` | `INTEGER` | `NOT NULL DEFAULT 1` | Optimistic lock and version counter. |

---

### 3.2. `source_to_canonical_mapping` (Active Serving View)
Maintains current active mapping from source systems to canonical IDs.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `source_system` | `TEXT` | `NOT NULL`, PK (1/2) | Source system identifier. |
| `source_record_id` | `TEXT` | `NOT NULL`, PK (2/2) | Source record identifier. |
| `canonical_id` | `TEXT` | `NOT NULL`, FK | References `canonical_entities(canonical_id)`. |
| `match_type` | `TEXT` | `NOT NULL` | Resolution mechanism: `EXACT_SOURCE_ID`, `EXACT_NATIONAL_ID`, `RULE_EMAIL`, `RULE_PHONE`, `RULE_COMPOSITE`, `NEW_CANONICAL`. |
| `matched_rule` | `TEXT` | Nullable | Name of specific matching rule that triggered. |
| `confidence_score` | `REAL` | `NOT NULL` | Confidence level between `0.0` and `1.0`. |
| `is_active` | `INTEGER` | `NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))` | Active flag for downstream analytical queries. |
| `created_at` | `TEXT` | `NOT NULL` | ISO-8601 timestamp when link was first established. |
| `updated_at` | `TEXT` | `NOT NULL` | ISO-8601 timestamp of last observation. |
| `last_run_id` | `TEXT` | `NOT NULL` | Lineage pointer to `pipeline_runs(run_id)`. |

---

### 3.3. `canonical_mapping_history` (SCD Type 2 Audit Trail)
Preserves immutable state changes over time without overwriting history.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `history_id` | `TEXT` | `PRIMARY KEY` | UUID uniquely identifying this historical interval. |
| `source_system` | `TEXT` | `NOT NULL`, Indexed | Source system identifier. |
| `source_record_id` | `TEXT` | `NOT NULL`, Indexed | Source record identifier. |
| `canonical_id` | `TEXT` | `NOT NULL`, Indexed | Canonical ID mapped during this interval. |
| `match_type` | `TEXT` | `NOT NULL` | Match type applied. |
| `matched_rule` | `TEXT` | Nullable | Specific rule invoked. |
| `effective_from` | `TEXT` | `NOT NULL` | ISO-8601 start timestamp of mapping validity. |
| `effective_to` | `TEXT` | Nullable | ISO-8601 end timestamp (`NULL` if currently active). |
| `is_current` | `INTEGER` | `NOT NULL CHECK (is_current IN (0, 1))` | `1` if current active state, `0` if historical. |
| `change_reason` | `TEXT` | `NOT NULL` | Reason code: `INITIAL_MAPPING`, `CANONICAL_RECLASSIFICATION`, `MERGE`, `MANUAL_OVERRIDE`. |
| `run_id` | `TEXT` | `NOT NULL`, Indexed | Pipeline execution run ID responsible for change. |

---

### 3.4. `unresolved_mappings` (Quarantine / Exceptions Table)
Captures rejected, malformed, contradictory, or ambiguous records.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `quarantine_id` | `TEXT` | `PRIMARY KEY` | Unique UUID for quarantine incident. |
| `run_id` | `TEXT` | `NOT NULL`, Indexed | Run ID during which error was caught. |
| `source_system` | `TEXT` | Nullable, Indexed | Originating system (or `'UNKNOWN'`). |
| `source_record_id` | `TEXT` | Nullable | Source record ID (or synthetic row index). |
| `payload_json` | `TEXT` | `NOT NULL` | Complete raw input JSON payload snapshot for triage. |
| `reason_code` | `TEXT` | `NOT NULL`, Indexed | Error classification (see Section 4). |
| `conflict_details` | `TEXT` | Nullable | JSON diagnostics explaining colliding IDs or rules. |
| `severity` | `TEXT` | `CHECK (severity IN ('WARNING', 'ERROR', 'CRITICAL'))` | Severity classification. |
| `status` | `TEXT` | `CHECK (status IN ('OPEN', 'RESOLVED', 'IGNORED'))` | Operational workflow status for data stewards. |
| `detected_at` | `TEXT` | `NOT NULL` | ISO-8601 timestamp when anomaly was quarantined. |

---

### 3.5. `pipeline_runs` (Operational Run Metrics Table)
Observability table recording batch run metadata and data quality metrics.

| Column Name | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `run_id` | `TEXT` | `PRIMARY KEY` | Deterministic run identifier (e.g. `run_20261111_120000_abc123`). |
| `pipeline_name` | `TEXT` | `NOT NULL` | Pipeline name identifier. |
| `batch_id` | `TEXT` | Nullable | Chunk or micro-batch identifier. |
| `source_file` | `TEXT` | Nullable | Source file path or stream partition. |
| `start_time` | `TEXT` | `NOT NULL` | ISO-8601 execution start timestamp. |
| `end_time` | `TEXT` | Nullable | ISO-8601 execution completion timestamp. |
| `duration_seconds`| `REAL` | Nullable | Total elapsed wall-clock execution time. |
| `status` | `TEXT` | `NOT NULL` | `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`. |
| `input_records_count` | `INTEGER` | `DEFAULT 0` | Total records ingested. |
| `valid_records_count` | `INTEGER` | `DEFAULT 0` | Records passing schema validation. |
| `mapped_existing_count` | `INTEGER` | `DEFAULT 0` | Records successfully linked to existing canonical IDs. |
| `created_canonical_count` | `INTEGER` | `DEFAULT 0` | Novel canonical entities provisioned. |
| `unresolved_count` | `INTEGER` | `DEFAULT 0` | Records quarantined due to conflicts or missing criteria. |
| `rejected_count` | `INTEGER` | `DEFAULT 0` | Records quarantined due to schema validation failures. |
| `duplicate_records_count`| `INTEGER` | `DEFAULT 0` | Intra-batch duplicates detected and handled. |
| `error_message` | `TEXT` | Nullable | Unhandled exception message if run failed. |

---

## 4. Error & Conflict Reason Codes

| Reason Code | Category | Severity | Description |
| :--- | :--- | :---: | :--- |
| `MALFORMED_INPUT` | Ingestion | `CRITICAL` | Input item is not a valid JSON dictionary or object. |
| `MISSING_REQUIRED_KEY` | Schema | `ERROR` | Missing or blank primary key (`source_system` or `source_record_id`). |
| `SCHEMA_VALIDATION_ERROR` | Schema | `ERROR` | Data type constraint violation (e.g. illegal date format). |
| `CONFLICT_ONE_TO_MANY_CANONICAL` | Entity Resolution | `ERROR` | Input record matched multiple distinct canonical entities across rules (cross-rule split identity). |
| `CONFLICT_AMBIGUOUS_RULE_MATCH` | Entity Resolution | `ERROR` | A single rule matched multiple candidate entities in master registry. |
| `CONFLICT_SOURCE_KEY_COLLISION` | Ingestion | `ERROR` | Duplicate source primary key in same batch with contradictory natural attributes. |
| `UNRESOLVED_INSUFFICIENT_ATTRIBUTES` | Entity Resolution | `WARNING` | Valid record lacks sufficient identifiers to link or establish identity. |
| `UNRESOLVED_AUTO_CREATE_DISABLED` | Configuration | `WARNING` | Record has no existing match and automatic creation is disabled. |

