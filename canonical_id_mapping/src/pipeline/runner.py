import os
import json
import csv
import uuid
from pathlib import Path
from typing import List, Dict, Any, Generator, Optional
from datetime import datetime, timezone

from ..config import PipelineConfig
from ..database.connection import init_db, get_db_context
from ..database.repository import CanonicalRepository
from .processor import CanonicalPipelineProcessor
from ..utils.logger import get_logger
from ..utils.metrics import PipelineMetrics

logger = get_logger("canonical_runner")

def read_records_from_file(file_path: str, chunk_size: int = 5000) -> Generator[List[Dict[str, Any]], None, None]:
    """Reads records from JSON, JSONL, or CSV file in memory-efficient chunks."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    ext = path.suffix.lower()

    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            content = json.load(f)
            if isinstance(content, list):
                for i in range(0, len(content), chunk_size):
                    yield content[i:i + chunk_size]
            elif isinstance(content, dict):
                yield [content]
            else:
                yield [content]

    elif ext in (".jsonl", ".ndjson"):
        batch = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    batch.append(json.loads(line_str))
                except Exception as e:
                    batch.append({"_raw_malformed_line": line_str, "_error": str(e)})
                if len(batch) >= chunk_size:
                    yield batch
                    batch = []
            if batch:
                yield batch

    elif ext == ".csv":
        batch = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Clean empty string attributes to None
                cleaned = {k: (v if v != "" else None) for k, v in row.items()}
                batch.append(cleaned)
                if len(batch) >= chunk_size:
                    yield batch
                    batch = []
            if batch:
                yield batch
    else:
        raise ValueError(f"Unsupported file format '{ext}'. Expected .json, .jsonl, or .csv")

def execute_pipeline(
    input_file: str,
    db_path: Optional[str] = None,
    batch_size: Optional[int] = None,
    run_id: Optional[str] = None,
    auto_create_canonical: bool = True
) -> PipelineMetrics:
    """Executes the complete canonical ID mapping pipeline on an input file."""
    config = PipelineConfig()
    target_db = db_path or config.db_path
    chunk_size = batch_size or config.batch_size
    current_run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # Ensure schema is initialized
    init_db(target_db)

    overall_metrics = PipelineMetrics(
        run_id=current_run_id,
        source_file=str(input_file),
        start_time=datetime.now(timezone.utc).isoformat()
    )

    total_chunks = 0
    try:
        with get_db_context(target_db) as conn:
            repo = CanonicalRepository(conn)
            processor = CanonicalPipelineProcessor(
                repo=repo,
                auto_create_canonical=auto_create_canonical
            )

            for chunk_idx, records in enumerate(read_records_from_file(input_file, chunk_size=chunk_size)):
                total_chunks += 1
                batch_id = f"batch_{chunk_idx:04d}"
                batch_metrics = processor.process_batch(
                    raw_records=records,
                    run_id=current_run_id,
                    batch_id=batch_id,
                    source_file=input_file
                )

                # Aggregate metrics
                overall_metrics.input_records_count += batch_metrics.input_records_count
                overall_metrics.valid_records_count += batch_metrics.valid_records_count
                overall_metrics.mapped_existing_count += batch_metrics.mapped_existing_count
                overall_metrics.created_canonical_count += batch_metrics.created_canonical_count
                overall_metrics.unresolved_count += batch_metrics.unresolved_count
                overall_metrics.rejected_count += batch_metrics.rejected_count
                overall_metrics.duplicate_records_count += batch_metrics.duplicate_records_count

            status = "SUCCESS" if (overall_metrics.rejected_count == 0 and overall_metrics.unresolved_count == 0) else "PARTIAL_SUCCESS"
            overall_metrics.finish(status=status)
            repo.record_pipeline_run(overall_metrics.to_dict())

    except Exception as e:
        logger.error(f"Pipeline failed catastrophically: {e}", exc_info=True)
        overall_metrics.finish(status="FAILED", error_message=str(e))
        # Record failure state outside the rolled back transaction
        try:
            with get_db_context(target_db) as fail_conn:
                CanonicalRepository(fail_conn).record_pipeline_run(overall_metrics.to_dict())
        except Exception:
            pass
        raise

    logger.info(f"Finished pipeline execution {current_run_id} across {total_chunks} chunks.")
    return overall_metrics

