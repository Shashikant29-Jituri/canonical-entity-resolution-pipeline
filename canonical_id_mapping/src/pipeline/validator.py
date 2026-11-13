from typing import List, Dict, Any, Tuple, Optional
from pydantic import ValidationError
from ..models.schemas import SourceRecordSchema
from ..models.entities import NormalizedRecord
from ..matching.normalizers import build_normalized_record

class ValidationResult:
    """Carries the outcome of validating a raw input batch."""
    def __init__(self):
        self.valid_records: List[NormalizedRecord] = []
        self.quarantined_records: List[Dict[str, Any]] = []
        self.duplicate_count: int = 0

class PipelineValidator:
    """Validates raw incoming batches against schema, checks nulls, and deduplicates batch keys."""

    @staticmethod
    def validate_batch(
        raw_records: List[Any],
        run_id: str
    ) -> ValidationResult:
        result = ValidationResult()
        seen_keys: Dict[Tuple[str, str], NormalizedRecord] = {}

        for idx, item in enumerate(raw_records):
            # Check 1: Record must be a dictionary / object
            if not isinstance(item, dict):
                result.quarantined_records.append({
                    "run_id": run_id,
                    "source_system": "UNKNOWN",
                    "source_record_id": f"ROW_{idx}",
                    "payload_json": str(item),
                    "reason_code": "MALFORMED_INPUT",
                    "conflict_details": {"error": f"Record must be a JSON object/dict, got {type(item).__name__}"},
                    "severity": "CRITICAL"
                })
                continue

            # Check 2: Pydantic schema validation
            try:
                validated_model = SourceRecordSchema(**item)
            except ValidationError as err:
                error_msgs = [f"{e['loc']}: {e['msg']}" for e in err.errors()]
                is_missing_key = (
                    any("Field required" in e for e in error_msgs) or
                    not item.get("source_system") or
                    not str(item.get("source_system", "")).strip() or
                    not item.get("source_record_id") or
                    not str(item.get("source_record_id", "")).strip()
                )
                reason_code = "MISSING_REQUIRED_KEY" if is_missing_key else "SCHEMA_VALIDATION_ERROR"
                result.quarantined_records.append({
                    "run_id": run_id,
                    "source_system": item.get("source_system", "UNKNOWN"),
                    "source_record_id": str(item.get("source_record_id", f"ROW_{idx}")),
                    "payload_json": item,
                    "reason_code": reason_code,
                    "conflict_details": {"validation_errors": error_msgs},
                    "severity": "ERROR"
                })
                continue

            # Check 3: Build normalized record
            try:
                norm_record = build_normalized_record(validated_model.model_dump())
            except Exception as e:
                result.quarantined_records.append({
                    "run_id": run_id,
                    "source_system": item.get("source_system"),
                    "source_record_id": str(item.get("source_record_id")),
                    "payload_json": item,
                    "reason_code": "NORMALIZATION_ERROR",
                    "conflict_details": {"error": str(e)},
                    "severity": "ERROR"
                })
                continue

            # Check 4: In-batch duplicate handling
            batch_key = (norm_record.source_system, norm_record.source_record_id)
            if batch_key in seen_keys:
                result.duplicate_count += 1
                prior = seen_keys[batch_key]
                # Compare critical natural attributes to check for intra-batch collision
                if (prior.email != norm_record.email or
                    prior.phone != norm_record.phone or
                    prior.national_id != norm_record.national_id):
                    result.quarantined_records.append({
                        "run_id": run_id,
                        "source_system": norm_record.source_system,
                        "source_record_id": norm_record.source_record_id,
                        "payload_json": item,
                        "reason_code": "CONFLICT_SOURCE_KEY_COLLISION",
                        "conflict_details": {
                            "message": "Duplicate source key in same batch with contradictory attributes",
                            "first_seen": prior.raw_payload,
                            "colliding_record": item
                        },
                        "severity": "ERROR"
                    })
                    continue
                else:
                    # Exactly identical or benign duplicate; skip redundant processing
                    continue

            seen_keys[batch_key] = norm_record
            result.valid_records.append(norm_record)

        return result
