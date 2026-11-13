# Data Reconciliation & Integrity Audit Report

**Generated:** 2026-11-11T16:40:34.191194+00:00  
**Database:** `data/canonical_store.db`  

---

## 1. Automated Integrity Checks

| Check Name | Status | Details |
| :--- | :---: | :--- |
| **Referential Integrity** | ✅ PASS | Active orphans: 0, History orphans: 0 |
| **Active Key Uniqueness** | ✅ PASS | Duplicate active keys: 0 |
| **SCD-2 Consistency** | ✅ PASS | Multi-current history violations: 0 |

---

## 2. Table Row Counts

| Table Name | Row Count |
| :--- | :---: |
| `canonical_entities` | 5 |
| `source_to_canonical_mapping` | 4 |
| `canonical_mapping_history` | 4 |
| `unresolved_mappings` | 6 |
| `pipeline_runs` | 1 |

---

## 3. Resolution & Match Distribution

| Match Type | Total Mappings |
| :--- | :---: |
| `RULE_PHONE` | 1 |
| `RULE_EMAIL` | 1 |
| `NEW_CANONICAL` | 1 |
| `EXACT_NATIONAL_ID` | 1 |

---

## 4. Quarantined & Unresolved Mappings Breakdown

| Reason Code | Severity | Quarantined Count |
| :--- | :---: | :---: |
| `CONFLICT_AMBIGUOUS_RULE_MATCH` | `ERROR` | 1 |
| `CONFLICT_ONE_TO_MANY_CANONICAL` | `ERROR` | 1 |
| `CONFLICT_SOURCE_KEY_COLLISION` | `ERROR` | 1 |
| `MISSING_REQUIRED_KEY` | `ERROR` | 1 |
| `SCHEMA_VALIDATION_ERROR` | `ERROR` | 1 |
| `UNRESOLVED_INSUFFICIENT_ATTRIBUTES` | `WARNING` | 1 |
