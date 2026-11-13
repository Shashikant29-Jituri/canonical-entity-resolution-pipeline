import argparse
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import init_db, get_db_context
from src.database.repository import CanonicalRepository
from src.pipeline.runner import execute_pipeline
from src.utils.logger import get_logger

logger = get_logger("run_pipeline_cli")

def seed_canonical_registry(db_path: str, seed_file: str) -> int:
    """Pre-populates canonical entities if provided."""
    path = Path(seed_file)
    if not path.exists():
        logger.warning(f"Seed file {seed_file} does not exist, skipping pre-seeding.")
        return 0

    with open(path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    inserted = 0
    with get_db_context(db_path) as conn:
        repo = CanonicalRepository(conn)
        for ent in entities:
            if not repo.get_canonical_entity(ent["canonical_id"]):
                repo.insert_canonical_entity(ent)
                inserted += 1
    logger.info(f"Pre-seeded {inserted} canonical master entities into {db_path}")
    return inserted

def main():
    parser = argparse.ArgumentParser(description="Run the Canonical ID Mapping & Entity Resolution Pipeline.")
    parser.add_argument("--input", type=str, required=True, help="Path to input data file (.json, .jsonl, .csv)")
    parser.add_argument("--db", type=str, default="data/canonical_store.db", help="Path to SQLite database")
    parser.add_argument("--seed-canonical", type=str, default=None, help="Path to pre-seed canonical entities JSON")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch processing chunk size")
    parser.add_argument("--run-id", type=str, default=None, help="Custom run ID")
    parser.add_argument("--no-auto-create", action="store_true", help="Disable automatic creation of novel canonical IDs")

    args = parser.parse_args()

    # Initialize DB
    init_db(args.db)

    # Optional seeding
    if args.seed_canonical:
        seed_canonical_registry(args.db, args.seed_canonical)

    logger.info(f"Executing pipeline on {args.input} -> DB: {args.db}")
    metrics = execute_pipeline(
        input_file=args.input,
        db_path=args.db,
        batch_size=args.batch_size,
        run_id=args.run_id,
        auto_create_canonical=not args.no_auto_create
    )

    print("\n" + "=" * 60)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 60)
    print(metrics.to_json())
    print("=" * 60)

    if metrics.status == "FAILED":
        sys.exit(1)

if __name__ == "__main__":
    main()

