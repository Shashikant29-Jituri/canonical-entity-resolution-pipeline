import sqlite3

def display_results(db_path: str = "data/canonical_store.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print("=" * 90)
    print("1. ACTIVE SOURCE-TO-CANONICAL MAPPINGS (source_to_canonical_mapping)")
    print("=" * 90)
    print(f"{'Source System':<20} | {'Source Record ID':<16} | {'Canonical ID':<14} | {'Match Type':<18} | {'Score'}")
    print("-" * 90)
    for r in conn.execute("SELECT source_system, source_record_id, canonical_id, match_type, confidence_score FROM source_to_canonical_mapping"):
        print(f"{r['source_system']:<20} | {r['source_record_id']:<16} | {r['canonical_id']:<14} | {r['match_type']:<18} | {r['confidence_score']:.2f}")

    print("\n" + "=" * 90)
    print("2. QUARANTINED & UNRESOLVED RECORDS (unresolved_mappings)")
    print("=" * 90)
    print(f"{'Source System':<20} | {'Source Record ID':<16} | {'Quarantine Reason':<36} | {'Severity'}")
    print("-" * 90)
    for r in conn.execute("SELECT source_system, source_record_id, reason_code, severity FROM unresolved_mappings"):
        src = r['source_system'] or "UNKNOWN"
        rid = r['source_record_id'] or "MISSING"
        print(f"{src:<20} | {rid:<16} | {r['reason_code']:<36} | {r['severity']}")

    print("\n" + "=" * 90)
    print("3. CANONICAL MASTER ENTITIES (canonical_entities)")
    print("=" * 90)
    print(f"{'Canonical ID':<14} | {'Name':<20} | {'Email':<25} | {'Phone':<12}")
    print("-" * 90)
    for r in conn.execute("SELECT canonical_id, primary_name, primary_email, primary_phone FROM canonical_entities"):
        name = r['primary_name'] or "-"
        email = r['primary_email'] or "-"
        phone = r['primary_phone'] or "-"
        print(f"{r['canonical_id']:<14} | {name:<20} | {email:<25} | {phone:<12}")

    print("=" * 90)
    conn.close()

if __name__ == "__main__":
    display_results()

