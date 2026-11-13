import os
from pathlib import Path
from dataclasses import dataclass

BASE_DIR = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class PipelineConfig:
    db_path: str = os.getenv("CANONICAL_DB_PATH", str(BASE_DIR / "data" / "canonical_store.db"))
    log_level: str = os.getenv("CANONICAL_LOG_LEVEL", "INFO")
    batch_size: int = int(os.getenv("CANONICAL_BATCH_SIZE", "5000"))
    auto_create_canonical: bool = os.getenv("CANONICAL_AUTO_CREATE", "True").lower() in ("true", "1", "yes")
    min_confidence_threshold: float = float(os.getenv("CANONICAL_MIN_CONFIDENCE", "0.70"))
    quarantine_conflicts: bool = True

