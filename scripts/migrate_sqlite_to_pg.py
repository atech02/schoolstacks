"""
scripts/migrate_sqlite_to_pg.py — Safe data exporter and migrator from SQLite to PostgreSQL.
Verifies record counts, preserves IDs, handles foreign key dependency order,
updates PostgreSQL primary key sequences, and validates data integrity.
"""
import os
import sys
import json
import sqlite3
from datetime import datetime

# Table dependency order for foreign key safety
TABLE_ORDER = [
    "schools",
    "users",
    "classes",
    "subjects",
    "terms",
    "subscriptions",
    "teachers",
    "students",
    "parents",
    "parent_students",
    "teacher_assignments",
    "attendance",
    "announcements",
    "notifications",
    "materials",
    "assignments",
    "submissions",
    "timetables",
    "fee_structures",
    "payments",
    "exams",
    "results",
    "activity_logs",
]


def export_sqlite_data(sqlite_path: str) -> dict:
    if not os.path.isfile(sqlite_path):
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    con = sqlite3.connect(sqlite_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    all_tables = {r[0] for r in cur.fetchall()}

    dump = {}
    for table in TABLE_ORDER:
        if table in all_tables:
            cur.execute(f'SELECT * FROM "{table}" ORDER BY id ASC;')
            rows = [dict(row) for row in cur.fetchall()]
            dump[table] = rows
            print(f"[EXPORT] Table '{table}': {len(rows)} records")
        else:
            dump[table] = []

    con.close()
    return dump


def save_backup_json(dump: dict, json_path: str):
    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, default=str)
    print(f"[BACKUP] Saved JSON snapshot to: {json_path}")


def import_to_postgres(pg_database_url: str, dump_data: dict) -> bool:
    """
    Safely import SQLite dump into target PostgreSQL database.
    Does not drop or truncate existing tables.
    """
    from sqlalchemy import create_engine, text
    import psycopg2

    # Clean URL format
    if pg_database_url.startswith("postgres://"):
        pg_database_url = pg_database_url.replace("postgres://", "postgresql://", 1)

    print(f"[MIGRATE] Connecting to target PostgreSQL...")
    engine = create_engine(pg_database_url, pool_pre_ping=True)

    with engine.begin() as conn:
        for table in TABLE_ORDER:
            rows = dump_data.get(table, [])
            if not rows:
                continue

            # Check if target already has rows
            current_count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            if current_count > 0:
                print(f"[MIGRATE] Table '{table}' already contains {current_count} rows. Skipping insertion to prevent overwrite.")
                continue

            print(f"[MIGRATE] Inserting {len(rows)} rows into '{table}'...")
            for row in rows:
                cols = list(row.keys())
                col_names = ", ".join([f'"{c}"' for c in cols])
                val_placeholders = ", ".join([f":{c}" for c in cols])
                insert_sql = text(f'INSERT INTO "{table}" ({col_names}) VALUES ({val_placeholders})')
                conn.execute(insert_sql, row)

            # Reset PostgreSQL sequence to MAX(id) if table has an id column
            try:
                max_id = conn.execute(text(f'SELECT MAX(id) FROM "{table}"')).scalar()
                if max_id:
                    conn.execute(text(f"SELECT setval(pg_get_serial_sequence('\"{table}\"', 'id'), :max_val)"), {"max_val": max_id})
                    print(f"  -> Reset sequence for '{table}' to {max_id}")
            except Exception as seq_err:
                # Some tables may not have serial id sequences
                pass

    print("[MIGRATE] Import completed. Running verification...")
    expected_counts = {t: len(dump_data.get(t, [])) for t in TABLE_ORDER}
    return verify_pg_migration_engine(engine, expected_counts)


def verify_pg_migration_engine(engine, expected_counts: dict) -> bool:
    from sqlalchemy import text
    all_matched = True
    print("\n--- Verifying PostgreSQL Record Counts ---")
    with engine.connect() as conn:
        for table, expected in expected_counts.items():
            if expected == 0:
                continue
            res = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
            match = res == expected
            status = "MATCH" if match else "MISMATCH"
            print(f"  [{status}] {table}: PostgreSQL={res}, Expected={expected}")
            if not match:
                all_matched = False
    return all_matched


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_path = os.path.join(base_dir, "instance", "edumanage.db")
    dump_data = export_sqlite_data(db_path)
    backup_file = os.path.join(base_dir, "instance", f"sqlite_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    save_backup_json(dump_data, backup_file)

    pg_url = os.environ.get("TARGET_DATABASE_URL")
    if pg_url:
        print("[MIGRATE] TARGET_DATABASE_URL detected, initiating import...")
        success = import_to_postgres(pg_url, dump_data)
        if success:
            print("[SUCCESS] All records verified in target PostgreSQL.")
        else:
            print("[WARNING] Some table counts did not match expected numbers.")
    else:
        print("[INFO] No TARGET_DATABASE_URL specified. Dump saved safely.")
