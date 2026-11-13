-- ============================================================================
-- Canonical ID Mapping & Entity Resolution Schema
-- Database: SQLite / ANSI-compliant SQL
-- ============================================================================

-- 1. Canonical Master Entities Table
CREATE TABLE IF NOT EXISTS canonical_entities (
    canonical_id TEXT PRIMARY KEY,
    primary_name TEXT,
    primary_email TEXT,
    primary_phone TEXT,
    national_id TEXT,
    postal_code TEXT,
    country TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    entity_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_canonical_email ON canonical_entities(primary_email);
CREATE INDEX IF NOT EXISTS idx_canonical_phone ON canonical_entities(primary_phone);
CREATE INDEX IF NOT EXISTS idx_canonical_national_id ON canonical_entities(national_id);
CREATE INDEX IF NOT EXISTS idx_canonical_name_zip ON canonical_entities(primary_name, postal_code);
CREATE INDEX IF NOT EXISTS idx_canonical_created ON canonical_entities(created_at DESC);

-- 2. Active Source-to-Canonical Serving Mapping Table
CREATE TABLE IF NOT EXISTS source_to_canonical_mapping (
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    match_type TEXT NOT NULL,
    matched_rule TEXT,
    confidence_score REAL NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_run_id TEXT NOT NULL,
    PRIMARY KEY (source_system, source_record_id),
    FOREIGN KEY (canonical_id) REFERENCES canonical_entities(canonical_id)
);

CREATE INDEX IF NOT EXISTS idx_mapping_canonical_id ON source_to_canonical_mapping(canonical_id);
CREATE INDEX IF NOT EXISTS idx_mapping_active ON source_to_canonical_mapping(is_active);
CREATE INDEX IF NOT EXISTS idx_mapping_canonical_active ON source_to_canonical_mapping(canonical_id, is_active);

-- 3. Canonical Mapping History (SCD Type 2 Audit Trail)
CREATE TABLE IF NOT EXISTS canonical_mapping_history (
    history_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    match_type TEXT NOT NULL,
    matched_rule TEXT,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
    change_reason TEXT NOT NULL,
    run_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_lookup ON canonical_mapping_history(source_system, source_record_id, is_current);
CREATE INDEX IF NOT EXISTS idx_history_canonical ON canonical_mapping_history(canonical_id);
CREATE INDEX IF NOT EXISTS idx_history_run_id ON canonical_mapping_history(run_id);

-- 4. Unresolved Mappings / Quarantine Table
CREATE TABLE IF NOT EXISTS unresolved_mappings (
    quarantine_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_system TEXT,
    source_record_id TEXT,
    payload_json TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    conflict_details TEXT,
    severity TEXT NOT NULL DEFAULT 'ERROR' CHECK (severity IN ('WARNING', 'ERROR', 'CRITICAL')),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'IGNORED')),
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_unresolved_run_id ON unresolved_mappings(run_id);
CREATE INDEX IF NOT EXISTS idx_unresolved_reason ON unresolved_mappings(reason_code);
CREATE INDEX IF NOT EXISTS idx_unresolved_source ON unresolved_mappings(source_system, source_record_id);

-- 5. Operational Pipeline Run Metrics Table
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    batch_id TEXT,
    source_file TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_seconds REAL,
    status TEXT NOT NULL,
    input_records_count INTEGER DEFAULT 0,
    valid_records_count INTEGER DEFAULT 0,
    mapped_existing_count INTEGER DEFAULT 0,
    created_canonical_count INTEGER DEFAULT 0,
    unresolved_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    duplicate_records_count INTEGER DEFAULT 0,
    error_message TEXT
);

-- Analytical / Reconciliation Views
CREATE VIEW IF NOT EXISTS v_active_mappings_summary AS
SELECT
    m.canonical_id,
    c.primary_name,
    c.primary_email,
    c.primary_phone,
    COUNT(m.source_record_id) AS total_source_records,
    GROUP_CONCAT(DISTINCT m.source_system) AS linked_source_systems,
    MIN(m.created_at) AS earliest_linked_at,
    MAX(m.updated_at) AS latest_linked_at
FROM source_to_canonical_mapping m
JOIN canonical_entities c ON m.canonical_id = c.canonical_id
WHERE m.is_active = 1
GROUP BY m.canonical_id, c.primary_name, c.primary_email, c.primary_phone;

CREATE VIEW IF NOT EXISTS v_unresolved_by_reason AS
SELECT
    reason_code,
    severity,
    COUNT(*) AS total_quarantined,
    COUNT(DISTINCT source_system) AS affected_systems,
    MIN(detected_at) AS first_seen,
    MAX(detected_at) AS last_seen
FROM unresolved_mappings
WHERE status = 'OPEN'
GROUP BY reason_code, severity;

