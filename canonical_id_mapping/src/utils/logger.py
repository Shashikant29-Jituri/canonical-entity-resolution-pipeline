import logging
import sys
import json
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "run_id"):
            log_obj["run_id"] = record.run_id
        if hasattr(record, "extra_data"):
            log_obj["extra"] = record.extra_data
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)

def get_logger(name: str = "canonical_pipeline", level: str = "INFO", as_json: bool = False) -> logging.Logger:
    """Configures and returns a consistent logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        handler = logging.StreamHandler(sys.stdout)
        if as_json:
            handler.setFormatter(JSONFormatter())
        else:
            fmt = logging.Formatter(
                fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.propagate = False
    return logger

