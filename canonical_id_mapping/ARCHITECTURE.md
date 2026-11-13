# Architectural Blueprint & System Design

## 1. Executive Summary
The Canonical ID Mapping system resolves source records originating from disparate systems into unified canonical master profiles. It handles identity fragmentation, prevents silent identity corruption from cross-attribute conflicts, maintains historical auditability, and guarantees idempotency.

---

## 2. End-to-End System Architecture

```mermaid
flowchart TD
    subgraph Ingestion ["1. INGESTION & VALIDATION"]
        A[Raw Input Stream / Files\nJSON, JSONL, CSV] --> B[PipelineValidator]
        B -->|Schema Violation / Missing PK / Malformed| C[Unresolved Quarantined Table\nstatus = OPEN]
        B -->|Valid Normalized Record| D[Matching Engine Orchestrator]
    end

    subgraph Resolution ["2. ENTITY RESOLUTION & CONFLICT DETECTION"]
        D --> R0[Tier 0: Exact Source Key Lookup]
        D --> R1[Tier 1: Exact National ID Match]
        D --> R2[Tier 2: Contact Match - Email / Phone]
        D --> R3[Tier 3: Composite Name + Postal Code]
        
        R0 & R1 & R2 & R3 --> CD[Conflict Detector]
        CD -->|Cross-Rule Divergence\ne.g. Email to CAN-1, Phone to CAN-2| Q1[Quarantine: CONFLICT_ONE_TO_MANY_CANONICAL]
        CD -->|Ambiguous Single Rule\ne.g. Duplicate Names in Zip| Q2[Quarantine: CONFLICT_AMBIGUOUS_RULE_MATCH]
        CD -->|Unanimous Single Candidate| HT[History Tracker - SCD Type 2]
        CD -->|No Candidate Match| NC[Novel Identity Evaluator]
    end

    subgraph Provisioning ["3. PROVISIONING & HISTORY"]
        NC -->|Sufficient Criteria| MC[Mint Deterministic CAN-ID\nvia SHA-256 Digest]
        NC -->|Insufficient Criteria| Q3[Quarantine: UNRESOLVED_INSUFFICIENT_ATTRIBUTES]
        MC --> CE[Insert canonical_entities]
        MC --> HT
        
        HT -->|State Changed\ne.g. CAN-A to CAN-B| S1[Close Old Interval: is_current=0\nOpen New Interval: is_current=1]
        HT -->|State Unchanged| S2[Touch updated_at & last_run_id]
        
        S1 & S2 --> SM[Upsert source_to_canonical_mapping]
        S1 --> CH[Insert canonical_mapping_history]
    end

    subgraph Observability ["4. OBSERVABILITY & AUDIT"]
        B & CD & HT --> PR[pipeline_runs Table\nMetrics, Latency, Status]
        SM & CH & CE & PR --> RC[scripts/run_reconciliation.py\nReferential Integrity & Conservation Audit]
    end
```

---

## 3. Data Processing Stages

### Stage 1: Validation & In-Batch De-duplication
- **Schema Validation**: Validates fields against `SourceRecordSchema` (Pydantic). Verifies required non-empty primary keys (`source_system`, `source_record_id`) and ISO-8601 formatting.
- **Normalizers**:
  - `email`: Trimmed, lowercased, validated against RFC regex.
  - `phone`: Non-digits stripped, leading country codes (`+1`) handled to yield standardized numeric representation.
  - `name`: Cleaned, lowercased, punctuation removed, business suffixes (`Inc`, `LLC`, `Corp`) stripped.
  - `national_id`: Uppercased, dashes/spaces stripped.
  - `postal_code`: Cleaned to standard 5-digit ZIP or alphanumeric postal code.
- **Intra-Batch Collision Check**:
  - If identical `(source_system, source_record_id)` with identical attributes appears in the same batch, it is deduplicated and counted in `duplicate_records_count`.
  - If identical source key appears with conflicting natural keys, it is quarantined immediately as `CONFLICT_SOURCE_KEY_COLLISION`.

### Stage 2: Matching Cascade & Precedence
1. **Tier 0: Exact Source Key Lookup** (`EXACT_SOURCE_ID`, Confidence 1.00):
   Checks if the source identifier is already mapped in `source_to_canonical_mapping`.
2. **Tier 1: Exact National ID** (`EXACT_NATIONAL_ID`, Confidence 1.00):
   Checks unique government / tax identifiers (`national_id`).
3. **Tier 2: Contact Identifier Rules**:
   - `RULE_EMAIL` (Confidence 0.95): Matches unique normalized contact email.
   - `RULE_PHONE` (Confidence 0.90): Matches unique normalized contact phone.
4. **Tier 3: Composite Deterministic Rule** (`RULE_COMPOSITE`, Confidence 0.85):
   Matches on combined `(normalized_name, postal_code)`.

### Stage 3: Conflict Detection & Ambiguity Quarantine
The system does not terminate greedily on the first rule. Instead, it evaluates across rules to detect multi-attribute divergence:
- **Cross-Rule Divergence (`CONFLICT_ONE_TO_MANY_CANONICAL`)**:
  Occurs when rule A (e.g. Email) resolves to `CAN-0001` while rule B (e.g. Phone) resolves to `CAN-0002`. Such records are quarantined in `unresolved_mappings` with complete diagnostic details.
- **Single-Rule Ambiguity (`CONFLICT_AMBIGUOUS_RULE_MATCH`)**:
  Occurs when a single composite query returns multiple candidate canonical records.

### Stage 4: SCD Type 2 History & Idempotency
- **Initial Mapping**: Creates an open-ended history record (`effective_from = now()`, `effective_to = NULL`, `is_current = 1`, `change_reason = 'INITIAL_MAPPING'`).
- **Reclassification**: Closes old interval (`effective_to = now()`, `is_current = 0`) and opens a new interval (`effective_from = now()`, `effective_to = NULL`, `is_current = 1`, `change_reason = 'CANONICAL_RECLASSIFICATION'`).
- **Idempotent Re-observation**: If the mapped `canonical_id` is identical, no new history rows are created. Only metadata timestamps are updated in the serving mapping table.

---

## 4. Analytical Views & Schema Relationships

```mermaid
erDiagram
    canonical_entities ||--o{ source_to_canonical_mapping : "resolves to"
    canonical_entities ||--o{ canonical_mapping_history : "tracks transitions"
    pipeline_runs ||--o{ source_to_canonical_mapping : "stamped with last_run_id"
    pipeline_runs ||--o{ canonical_mapping_history : "created by run_id"
    pipeline_runs ||--o{ unresolved_mappings : "quarantined during run_id"

    canonical_entities {
        text canonical_id PK
        text primary_name
        text primary_email
        text primary_phone
        text national_id
        text postal_code
        text country
        text created_at
        text updated_at
        integer entity_version
    }

    source_to_canonical_mapping {
        text source_system PK
        text source_record_id PK
        text canonical_id FK
        text match_type
        text matched_rule
        real confidence_score
        integer is_active
        text created_at
        text updated_at
        text last_run_id FK
    }

    canonical_mapping_history {
        text history_id PK
        text source_system
        text source_record_id
        text canonical_id FK
        text match_type
        text matched_rule
        text effective_from
        text effective_to
        integer is_current
        text change_reason
        text run_id FK
    }

    unresolved_mappings {
        text quarantine_id PK
        text run_id FK
        text source_system
        text source_record_id
        text payload_json
        text reason_code
        text conflict_details
        text severity
        text status
        text detected_at
    }

    pipeline_runs {
        text run_id PK
        text pipeline_name
        text batch_id
        text source_file
        text start_time
        text end_time
        real duration_seconds
        text status
        integer input_records_count
        integer valid_records_count
        integer mapped_existing_count
        integer created_canonical_count
        integer unresolved_count
        integer rejected_count
        integer duplicate_records_count
        text error_message
    }
```

