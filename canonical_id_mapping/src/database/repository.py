import sqlite3
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
import uuid

class CanonicalRepository:
    """Encapsulates all database operations for canonical mappings and entities."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # --- Canonical Entities ---
    def get_canonical_entity(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM canonical_entities WHERE canonical_id = ?",
            (canonical_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def find_canonical_by_national_id(self, national_id: str) -> List[str]:
        if not national_id:
            return []
        cursor = self.conn.execute(
            "SELECT canonical_id FROM canonical_entities WHERE national_id = ?",
            (national_id,)
        )
        return [row["canonical_id"] for row in cursor.fetchall()]

    def find_canonical_by_email(self, email: str) -> List[str]:
        if not email:
            return []
        cursor = self.conn.execute(
            "SELECT canonical_id FROM canonical_entities WHERE primary_email = ?",
            (email,)
        )
        return [row["canonical_id"] for row in cursor.fetchall()]

    def find_canonical_by_phone(self, phone: str) -> List[str]:
        if not phone:
            return []
        cursor = self.conn.execute(
            "SELECT canonical_id FROM canonical_entities WHERE primary_phone = ?",
            (phone,)
        )
        return [row["canonical_id"] for row in cursor.fetchall()]

    def find_canonical_by_composite(self, primary_name: str, postal_code: str) -> List[str]:
        if not primary_name or not postal_code:
            return []
        cursor = self.conn.execute(
            "SELECT canonical_id FROM canonical_entities WHERE primary_name = ? AND postal_code = ?",
            (primary_name, postal_code)
        )
        return [row["canonical_id"] for row in cursor.fetchall()]

    def insert_canonical_entity(self, entity: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO canonical_entities (
                canonical_id, primary_name, primary_email, primary_phone,
                national_id, postal_code, country, created_at, updated_at, entity_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity["canonical_id"],
                entity.get("primary_name"),
                entity.get("primary_email"),
                entity.get("primary_phone"),
                entity.get("national_id"),
                entity.get("postal_code"),
                entity.get("country"),
                entity["created_at"],
                entity["updated_at"],
                entity.get("entity_version", 1),
            )
        )

    # --- Source to Canonical Active Mapping ---
    def get_active_mapping(self, source_system: str, source_record_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT * FROM source_to_canonical_mapping
            WHERE source_system = ? AND source_record_id = ? AND is_active = 1
            """,
            (source_system, source_record_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_mapping(self, mapping: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO source_to_canonical_mapping (
                source_system, source_record_id, canonical_id, match_type,
                matched_rule, confidence_score, is_active, created_at, updated_at, last_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_system, source_record_id) DO UPDATE SET
                canonical_id = excluded.canonical_id,
                match_type = excluded.match_type,
                matched_rule = excluded.matched_rule,
                confidence_score = excluded.confidence_score,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at,
                last_run_id = excluded.last_run_id
            """,
            (
                mapping["source_system"],
                mapping["source_record_id"],
                mapping["canonical_id"],
                mapping["match_type"],
                mapping.get("matched_rule"),
                mapping["confidence_score"],
                mapping.get("is_active", 1),
                mapping["created_at"],
                mapping["updated_at"],
                mapping["last_run_id"],
            )
        )

    # --- Canonical Mapping History (SCD Type 2) ---
    def close_current_history(self, source_system: str, source_record_id: str, effective_to: str) -> None:
        self.conn.execute(
            """
            UPDATE canonical_mapping_history
            SET is_current = 0, effective_to = ?
            WHERE source_system = ? AND source_record_id = ? AND is_current = 1
            """,
            (effective_to, source_system, source_record_id)
        )

    def insert_history(self, history: Dict[str, Any]) -> None:
        history_id = history.get("history_id") or str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO canonical_mapping_history (
                history_id, source_system, source_record_id, canonical_id,
                match_type, matched_rule, effective_from, effective_to,
                is_current, change_reason, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                history["source_system"],
                history["source_record_id"],
                history["canonical_id"],
                history["match_type"],
                history.get("matched_rule"),
                history["effective_from"],
                history.get("effective_to"),
                history.get("is_current", 1),
                history["change_reason"],
                history["run_id"],
            )
        )

    def get_mapping_history(self, source_system: str, source_record_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT * FROM canonical_mapping_history
            WHERE source_system = ? AND source_record_id = ?
            ORDER BY effective_from ASC
            """,
            (source_system, source_record_id)
        )
        return [dict(row) for row in cursor.fetchall()]

    # --- Unresolved Mappings / Quarantine ---
    def insert_unresolved(self, record: Dict[str, Any]) -> None:
        quarantine_id = record.get("quarantine_id") or str(uuid.uuid4())
        payload = record["payload_json"]
        if isinstance(payload, dict):
            payload = json.dumps(payload)

        conflict_details = record.get("conflict_details")
        if isinstance(conflict_details, (dict, list)):
            conflict_details = json.dumps(conflict_details)

        self.conn.execute(
            """
            INSERT INTO unresolved_mappings (
                quarantine_id, run_id, source_system, source_record_id,
                payload_json, reason_code, conflict_details, severity, status, detected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quarantine_id,
                record["run_id"],
                record.get("source_system"),
                record.get("source_record_id"),
                payload,
                record["reason_code"],
                conflict_details,
                record.get("severity", "ERROR"),
                record.get("status", "OPEN"),
                record.get("detected_at") or datetime.now(timezone.utc).isoformat(),
            )
        )

    def get_unresolved_records(self, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if run_id:
            cursor = self.conn.execute(
                "SELECT * FROM unresolved_mappings WHERE run_id = ?",
                (run_id,)
            )
        else:
            cursor = self.conn.execute("SELECT * FROM unresolved_mappings ORDER BY detected_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    # --- Pipeline Runs Metrics ---
    def record_pipeline_run(self, metrics: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO pipeline_runs (
                run_id, pipeline_name, batch_id, source_file, start_time,
                end_time, duration_seconds, status, input_records_count,
                valid_records_count, mapped_existing_count, created_canonical_count,
                unresolved_count, rejected_count, duplicate_records_count, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                end_time = excluded.end_time,
                duration_seconds = excluded.duration_seconds,
                status = excluded.status,
                input_records_count = excluded.input_records_count,
                valid_records_count = excluded.valid_records_count,
                mapped_existing_count = excluded.mapped_existing_count,
                created_canonical_count = excluded.created_canonical_count,
                unresolved_count = excluded.unresolved_count,
                rejected_count = excluded.rejected_count,
                duplicate_records_count = excluded.duplicate_records_count,
                error_message = excluded.error_message
            """,
            (
                metrics["run_id"],
                metrics.get("pipeline_name", "canonical_id_pipeline"),
                metrics.get("batch_id"),
                metrics.get("source_file"),
                metrics["start_time"],
                metrics.get("end_time"),
                metrics.get("duration_seconds", 0.0),
                metrics.get("status", "STARTED"),
                metrics.get("input_records_count", 0),
                metrics.get("valid_records_count", 0),
                metrics.get("mapped_existing_count", 0),
                metrics.get("created_canonical_count", 0),
                metrics.get("unresolved_count", 0),
                metrics.get("rejected_count", 0),
                metrics.get("duplicate_records_count", 0),
                metrics.get("error_message"),
            )
        )

    def get_pipeline_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?",
            (run_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    # --- Reconciliation & Audit Queries ---
    def get_reconciliation_summary(self) -> Dict[str, Any]:
        """Calculates key counts and aggregates across tables to detect drift or anomalies."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) AS total FROM canonical_entities")
        total_canonical = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM source_to_canonical_mapping WHERE is_active = 1")
        total_active_mappings = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM canonical_mapping_history")
        total_history_records = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM unresolved_mappings")
        total_unresolved = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT match_type, COUNT(*) as count
            FROM source_to_canonical_mapping
            WHERE is_active = 1
            GROUP BY match_type
            """
        )
        match_type_distribution = {row["match_type"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT reason_code, COUNT(*) as count
            FROM unresolved_mappings
            GROUP BY reason_code
            """
        )
        unresolved_distribution = {row["reason_code"]: row["count"] for row in cursor.fetchall()}

        # Referential integrity check: orphan mappings (mappings pointing to non-existent canonical IDs)
        cursor.execute(
            """
            SELECT COUNT(*) AS orphan_count
            FROM source_to_canonical_mapping m
            LEFT JOIN canonical_entities c ON m.canonical_id = c.canonical_id
            WHERE c.canonical_id IS NULL
            """
        )
        orphan_mappings = cursor.fetchone()["orphan_count"]

        return {
            "total_canonical_entities": total_canonical,
            "total_active_mappings": total_active_mappings,
            "total_history_records": total_history_records,
            "total_unresolved_records": total_unresolved,
            "orphan_mappings_count": orphan_mappings,
            "match_type_distribution": match_type_distribution,
            "unresolved_distribution": unresolved_distribution,
        }

