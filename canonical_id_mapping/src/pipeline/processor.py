from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from ..database.repository import CanonicalRepository
from ..models.entities import NormalizedRecord, MatchResult
from ..matching.engine import MatchingEngine
from .validator import PipelineValidator, ValidationResult
from .history_tracker import HistoryTracker
from ..utils.metrics import PipelineMetrics
from ..utils.logger import get_logger

logger = get_logger("canonical_processor")

class CanonicalPipelineProcessor:
    """
    Main processor orchestrating ingestion, validation, matching,
    conflict handling, persistence, and audit metrics.
    """

    def __init__(
        self,
        repo: CanonicalRepository,
        matching_engine: Optional[MatchingEngine] = None,
        history_tracker: Optional[HistoryTracker] = None,
        auto_create_canonical: bool = True
    ):
        self.repo = repo
        self.matching_engine = matching_engine or MatchingEngine(
            repo=self.repo,
            auto_create_canonical=auto_create_canonical
        )
        self.history_tracker = history_tracker or HistoryTracker(self.repo)

    def process_batch(
        self,
        raw_records: List[Any],
        run_id: str,
        batch_id: Optional[str] = None,
        source_file: Optional[str] = None
    ) -> PipelineMetrics:
        """Processes a single batch of records atomically."""
        metrics = PipelineMetrics(
            run_id=run_id,
            batch_id=batch_id,
            source_file=source_file,
            input_records_count=len(raw_records)
        )

        logger.info(f"Starting processing for run_id={run_id}, batch_id={batch_id}, records={len(raw_records)}")

        # Step 1: Validation
        val_result: ValidationResult = PipelineValidator.validate_batch(raw_records, run_id)
        metrics.rejected_count = len(val_result.quarantined_records)
        metrics.duplicate_records_count = val_result.duplicate_count
        metrics.valid_records_count = len(val_result.valid_records)

        # Persist validation quarantine records
        for q_rec in val_result.quarantined_records:
            self.repo.insert_unresolved(q_rec)

        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 2: Matching and Entity Resolution for valid records
        for norm_rec in val_result.valid_records:
            match_res: MatchResult = self.matching_engine.resolve(norm_rec)

            if match_res.is_unresolved or match_res.is_conflict:
                metrics.unresolved_count += 1
                self.repo.insert_unresolved({
                    "run_id": run_id,
                    "source_system": norm_rec.source_system,
                    "source_record_id": norm_rec.source_record_id,
                    "payload_json": norm_rec.raw_payload,
                    "reason_code": match_res.unresolved_reason or "UNRESOLVED_UNKNOWN",
                    "conflict_details": match_res.conflict_details,
                    "severity": "ERROR" if match_res.is_conflict else "WARNING",
                    "status": "OPEN",
                    "detected_at": now_iso
                })
                continue

            # Case: Novel canonical entity created
            if match_res.is_new_canonical:
                canonical_id = match_res.canonical_id
                # Check if entity already registered in repository (safe check)
                existing_entity = self.repo.get_canonical_entity(canonical_id)
                if not existing_entity:
                    self.repo.insert_canonical_entity({
                        "canonical_id": canonical_id,
                        "primary_name": norm_rec.raw_name,
                        "primary_email": norm_rec.email,
                        "primary_phone": norm_rec.phone,
                        "national_id": norm_rec.national_id,
                        "postal_code": norm_rec.postal_code,
                        "country": norm_rec.country,
                        "created_at": now_iso,
                        "updated_at": now_iso,
                        "entity_version": 1
                    })
                    metrics.created_canonical_count += 1
                else:
                    metrics.mapped_existing_count += 1

                self.history_tracker.apply_mapping(norm_rec, match_res, run_id, now_iso)

            # Case: Mapped to existing canonical entity
            else:
                metrics.mapped_existing_count += 1
                self.history_tracker.apply_mapping(norm_rec, match_res, run_id, now_iso)

        status = "SUCCESS" if (metrics.rejected_count == 0 and metrics.unresolved_count == 0) else "PARTIAL_SUCCESS"
        metrics.finish(status=status)

        # Record operational metrics in DB
        self.repo.record_pipeline_run(metrics.to_dict())

        logger.info(
            f"Run completed: status={metrics.status}, valid={metrics.valid_records_count}, "
            f"mapped={metrics.mapped_existing_count}, created={metrics.created_canonical_count}, "
            f"unresolved={metrics.unresolved_count}, rejected={metrics.rejected_count}"
        )
        return metrics

