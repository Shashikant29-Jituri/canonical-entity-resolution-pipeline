from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json

@dataclass
class PipelineMetrics:
    run_id: str
    pipeline_name: str = "canonical_id_pipeline"
    batch_id: Optional[str] = None
    source_file: Optional[str] = None
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    status: str = "STARTED"  # STARTED, SUCCESS, FAILED, PARTIAL_SUCCESS
    input_records_count: int = 0
    valid_records_count: int = 0
    mapped_existing_count: int = 0
    created_canonical_count: int = 0
    unresolved_count: int = 0
    rejected_count: int = 0
    duplicate_records_count: int = 0
    error_message: Optional[str] = None

    def finish(self, status: str = "SUCCESS", error_message: Optional[str] = None):
        self.end_time = datetime.now(timezone.utc).isoformat()
        t_start = datetime.fromisoformat(self.start_time)
        t_end = datetime.fromisoformat(self.end_time)
        self.duration_seconds = round((t_end - t_start).total_seconds(), 4)
        self.status = status
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

