import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

def get_connection(db_path: str, timeout: float = 30.0) -> sqlite3.Connection:
    """
    Creates and configures a SQLite connection with WAL mode and foreign key enforcement.
    """
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db(db_path: str) -> None:
    """Initializes tables and indexes from schema.sql."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()

@contextmanager
def get_db_context(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager providing an ACID transaction scope.
    Automatically commits on success or rolls back on exception.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

