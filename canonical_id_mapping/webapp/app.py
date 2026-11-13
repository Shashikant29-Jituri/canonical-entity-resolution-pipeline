import os
import sys
import json
import sqlite3
from pathlib import Path
import werkzeug

# Ensure compatibility between Werkzeug 3.x and Flask 2.3.x
if not hasattr(werkzeug, "__version__"):
    try:
        import importlib.metadata
        werkzeug.__version__ = importlib.metadata.version("werkzeug")
    except Exception:
        werkzeug.__version__ = "3.1.8"

from flask import Flask, render_template, request, jsonify, send_file

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import get_connection, init_db
from src.database.repository import CanonicalRepository
from src.pipeline.runner import execute_pipeline
from scripts.run_pipeline import seed_canonical_registry
from src.matching.normalizers import build_normalized_record
from src.models.schemas import SourceRecordSchema
from src.matching.engine import MatchingEngine
from src.pipeline.history_tracker import HistoryTracker
from scripts.ingest_external_dataset import convert_external_dataset

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
DB_PATH = os.getenv("CANONICAL_DB_PATH", "data/canonical_store.db")

# Ensure DB exists
init_db(DB_PATH)

def get_db():
    conn = get_connection(DB_PATH)
    return conn

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    conn = get_db()
    repo = CanonicalRepository(conn)
    summary = repo.get_reconciliation_summary()

    # Get recent pipeline runs
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pipeline_runs ORDER BY start_time DESC LIMIT 5")
    runs = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return jsonify({
        "status": "success",
        "summary": summary,
        "recent_runs": runs
    })

@app.route("/api/mappings", methods=["GET"])
def api_mappings():
    search = request.args.get("search", "").strip().lower()
    source_system = request.args.get("source_system", "").strip()
    match_type = request.args.get("match_type", "").strip()

    conn = get_db()
    query = """
        SELECT m.*, c.primary_name, c.primary_email, c.primary_phone
        FROM source_to_canonical_mapping m
        LEFT JOIN canonical_entities c ON m.canonical_id = c.canonical_id
        WHERE m.is_active = 1
    """
    params = []

    if source_system:
        query += " AND m.source_system = ?"
        params.append(source_system)
    if match_type:
        query += " AND m.match_type = ?"
        params.append(match_type)
    if search:
        query += """ AND (
            LOWER(m.source_record_id) LIKE ? OR
            LOWER(m.canonical_id) LIKE ? OR
            LOWER(c.primary_name) LIKE ? OR
            LOWER(c.primary_email) LIKE ?
        )"""
        s_param = f"%{search}%"
        params.extend([s_param, s_param, s_param, s_param])

    query += " ORDER BY m.updated_at DESC LIMIT 200"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    # Fetch all distinct source systems for complete filter population
    all_systems = [r[0] for r in conn.execute("SELECT DISTINCT source_system FROM source_to_canonical_mapping ORDER BY source_system").fetchall()]
    conn.close()

    return jsonify({"status": "success", "count": len(rows), "data": rows, "systems": all_systems})

@app.route("/api/entities", methods=["GET"])
def api_entities():
    search = request.args.get("search", "").strip().lower()
    conn = get_db()
    
    # Fast subquery on indexed canonical entities with subqueries for links
    if search:
        query = """
            SELECT c.*,
                   (SELECT COUNT(*) FROM source_to_canonical_mapping m WHERE m.canonical_id = c.canonical_id AND m.is_active = 1) AS linked_records_count,
                   (SELECT GROUP_CONCAT(DISTINCT m.source_system) FROM source_to_canonical_mapping m WHERE m.canonical_id = c.canonical_id AND m.is_active = 1) AS linked_systems
            FROM (
                SELECT * FROM canonical_entities
                WHERE LOWER(canonical_id) LIKE ? 
                   OR LOWER(primary_name) LIKE ? 
                   OR LOWER(COALESCE(national_id, '')) LIKE ?
                   OR LOWER(COALESCE(primary_email, '')) LIKE ?
                   OR LOWER(COALESCE(primary_phone, '')) LIKE ?
                ORDER BY created_at DESC LIMIT 200
            ) c
        """
        s_param = f"%{search}%"
        rows = [dict(r) for r in conn.execute(query, (s_param, s_param, s_param, s_param, s_param)).fetchall()]
    else:
        query = """
            SELECT c.*,
                   (SELECT COUNT(*) FROM source_to_canonical_mapping m WHERE m.canonical_id = c.canonical_id AND m.is_active = 1) AS linked_records_count,
                   (SELECT GROUP_CONCAT(DISTINCT m.source_system) FROM source_to_canonical_mapping m WHERE m.canonical_id = c.canonical_id AND m.is_active = 1) AS linked_systems
            FROM (
                SELECT * FROM canonical_entities ORDER BY created_at DESC LIMIT 200
            ) c
        """
        rows = [dict(r) for r in conn.execute(query).fetchall()]
    conn.close()
    return jsonify({"status": "success", "count": len(rows), "data": rows})

@app.route("/api/unresolved", methods=["GET"])
def api_unresolved():
    reason = request.args.get("reason", "").strip()
    status = request.args.get("status", "").strip()

    conn = get_db()
    query = "SELECT * FROM unresolved_mappings WHERE 1=1"
    params = []

    if reason:
        query += " AND reason_code = ?"
        params.append(reason)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY detected_at DESC LIMIT 200"
    rows = []
    for r in conn.execute(query, params).fetchall():
        item = dict(r)
        try:
            item["payload_json"] = json.loads(item["payload_json"])
        except Exception:
            pass
        try:
            item["conflict_details"] = json.loads(item["conflict_details"]) if item["conflict_details"] else None
        except Exception:
            pass
        rows.append(item)

    conn.close()
    return jsonify({"status": "success", "count": len(rows), "data": rows})

@app.route("/api/history", methods=["GET"])
def api_history():
    source_system = request.args.get("source_system", "").strip()
    source_record_id = request.args.get("source_record_id", "").strip()

    if not source_system or not source_record_id:
        return jsonify({"status": "error", "message": "source_system and source_record_id required"}), 400

    conn = get_db()
    repo = CanonicalRepository(conn)
    history = repo.get_mapping_history(source_system, source_record_id)
    conn.close()

    return jsonify({"status": "success", "data": history})

@app.route("/api/ingest-single", methods=["POST"])
def api_ingest_single():
    """Live interactive testing: resolves a single record on the fly."""
    data = request.json or {}
    try:
        validated = SourceRecordSchema(**data)
    except Exception as e:
        return jsonify({
            "status": "validation_error",
            "message": str(e),
            "reason_code": "SCHEMA_VALIDATION_ERROR"
        }), 400

    conn = get_db()
    repo = CanonicalRepository(conn)
    engine = MatchingEngine(repo=repo, auto_create_canonical=True)

    norm = build_normalized_record(validated.model_dump())
    result = engine.resolve(norm)

    conn.close()

    candidates_summary = [
        {
            "canonical_id": c.canonical_id,
            "rule": c.rule_name,
            "match_type": c.match_type,
            "confidence": c.confidence,
            "matched_value": c.matched_value
        }
        for c in result.all_candidates
    ]

    return jsonify({
        "status": "success",
        "resolved_canonical_id": result.canonical_id,
        "match_type": result.match_type,
        "matched_rule": result.matched_rule,
        "confidence_score": result.confidence_score,
        "is_conflict": result.is_conflict,
        "conflict_type": result.conflict_type,
        "conflict_details": result.conflict_details,
        "is_new_canonical": result.is_new_canonical,
        "is_unresolved": result.is_unresolved,
        "unresolved_reason": result.unresolved_reason,
        "candidates_evaluated": candidates_summary
    })

@app.route("/api/load-genuine-data", methods=["POST"])
def api_load_genuine_data():
    """Runs the genuine real-world tech-leaders dataset into the database."""
    seed_file = "data/genuine/seed_master_registry.json"
    data_file = "data/genuine/genuine_source_records.json"

    # Pre-seed genuine registry
    seed_canonical_registry(DB_PATH, seed_file)

    # Execute pipeline
    metrics = execute_pipeline(
        input_file=data_file,
        db_path=DB_PATH,
        auto_create_canonical=True
    )

    return jsonify({
        "status": "success",
        "message": "Genuine multi-system dataset loaded and resolved successfully!",
        "metrics": metrics.to_dict()
    })

@app.route("/api/resolve-quarantine", methods=["POST"])
def api_resolve_quarantine():
    data = request.json or {}
    quarantine_id = data.get("quarantine_id")
    new_status = data.get("status", "RESOLVED")

    if not quarantine_id:
        return jsonify({"status": "error", "message": "quarantine_id required"}), 400

    conn = get_db()
    conn.execute(
        "UPDATE unresolved_mappings SET status = ? WHERE quarantine_id = ?",
        (new_status, quarantine_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"Quarantine record {quarantine_id} updated to {new_status}"})

@app.route("/api/upload", methods=["POST"])
def api_upload_dataset():
    """Accepts single or multiple user-uploaded CSV / JSON / JSONL files and ingests them dynamically."""
    uploaded_files = request.files.getlist("files")
    if not uploaded_files or (len(uploaded_files) == 1 and not uploaded_files[0].filename):
        if "file" in request.files and request.files["file"].filename:
            uploaded_files = [request.files["file"]]
        else:
            return jsonify({"status": "error", "message": "No files uploaded"}), 400

    # Default to clearing previous/demo records so ONLY uploaded datasets appear
    clear_existing = request.form.get("clear_existing", "true").lower() in ("true", "1", "yes")
    if clear_existing:
        conn = get_db()
        for tbl in [
            "source_to_canonical_mapping",
            "canonical_mapping_history",
            "unresolved_mappings",
            "canonical_entities",
            "pipeline_runs"
        ]:
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
        conn.close()

    custom_system_name = request.form.get("source_system", "").strip()

    file_results = []
    total_input = 0
    total_valid = 0
    total_mapped = 0
    total_created = 0
    total_unresolved = 0
    total_rejected = 0

    for idx, uploaded_file in enumerate(uploaded_files):
        if not uploaded_file.filename:
            continue

        raw_name = uploaded_file.filename
        safe_name = werkzeug.utils.secure_filename(raw_name)
        if not safe_name:
            safe_name = f"dataset_{idx+1}.csv"

        # Determine source system name
        if custom_system_name and len(uploaded_files) == 1:
            source_system = custom_system_name
        else:
            source_system = Path(safe_name).stem.lower().replace("-", "_").replace(" ", "_")

        saved_path = UPLOAD_DIR / safe_name
        uploaded_file.save(str(saved_path))

        # Convert to normalized pipeline format
        norm_jsonl = UPLOAD_DIR / f"norm_{Path(safe_name).stem}_{idx}.jsonl"
        try:
            converted_count = convert_external_dataset(
                input_file=str(saved_path),
                output_jsonl=str(norm_jsonl),
                source_system=source_system
            )
        except Exception as e:
            file_results.append({
                "filename": raw_name,
                "status": "error",
                "error": f"Failed to parse file: {str(e)}"
            })
            continue

        # Execute resolution pipeline
        try:
            metrics = execute_pipeline(
                input_file=str(norm_jsonl),
                db_path=DB_PATH,
                auto_create_canonical=True
            )
            m_dict = metrics.to_dict()
            file_results.append({
                "filename": raw_name,
                "source_system": source_system,
                "status": "success",
                "records_count": metrics.input_records_count,
                "valid_count": metrics.valid_records_count,
                "mapped_existing": metrics.mapped_existing_count,
                "created_canonical": metrics.created_canonical_count,
                "unresolved_conflicts": metrics.unresolved_count,
                "rejected_count": metrics.rejected_count
            })

            total_input += metrics.input_records_count
            total_valid += metrics.valid_records_count
            total_mapped += metrics.mapped_existing_count
            total_created += metrics.created_canonical_count
            total_unresolved += metrics.unresolved_count
            total_rejected += metrics.rejected_count

        except Exception as e:
            file_results.append({
                "filename": raw_name,
                "status": "error",
                "error": f"Pipeline failure: {str(e)}"
            })

    successful_files = [f for f in file_results if f["status"] == "success"]
    if not successful_files:
        return jsonify({
            "status": "error",
            "message": "All uploaded files failed processing",
            "details": file_results
        }), 400

    msg = f"Processed {len(successful_files)} dataset(s): {total_input:,} total records ingested, {total_mapped:,} linked to existing canonical entities, {total_created:,} novel canonical entities created, and {total_unresolved:,} conflicts quarantined."

    return jsonify({
        "status": "success",
        "message": msg,
        "summary": {
            "files_processed_count": len(successful_files),
            "total_input_records": total_input,
            "total_valid_records": total_valid,
            "total_mapped_existing": total_mapped,
            "total_created_canonical": total_created,
            "total_unresolved_conflicts": total_unresolved,
            "total_rejected_records": total_rejected
        },
        "file_details": file_results
    })

@app.route("/benchmark-file/<filename>", methods=["GET"])
def get_benchmark_file(filename):
    """Serves sample benchmark datasets (e.g. Table A & Table B) for 1-click testing."""
    benchmark_dir = Path("data/benchmark_tables").resolve()
    safe_name = werkzeug.utils.secure_filename(filename)
    target = benchmark_dir / safe_name
    if not target.exists():
        return jsonify({"status": "error", "message": f"File {filename} not found"}), 404
    return send_file(str(target), mimetype="text/csv", as_attachment=True, download_name=safe_name)

@app.route("/api/reset-database", methods=["POST"])
def api_reset_database():
    """Wipes the database and re-initializes fresh empty schema."""
    conn = get_db()
    cursor = conn.cursor()
    tables = [
        "source_to_canonical_mapping",
        "canonical_mapping_history",
        "unresolved_mappings",
        "canonical_entities",
        "pipeline_runs"
    ]
    for tbl in tables:
        cursor.execute(f"DELETE FROM {tbl}")
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Database reset to clean state."})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Starting Canonical ID Mapping Web Portal on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
