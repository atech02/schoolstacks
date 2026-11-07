"""
migrations_helper.py — Safe, non-destructive schema evolution helper.
Ensures existing databases (SQLite or PostgreSQL) gain the Lipila and multi-tenant
reconciliation columns without dropping tables or losing historical records.
"""
import logging
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = {
    "schools": [
        ("lipila_customer_ref", "VARCHAR(100)"),
        ("lipila_subscription_ref", "VARCHAR(100)"),
        ("last_activity_at", "TIMESTAMP"),
        ("suspended_at", "TIMESTAMP"),
        ("suspension_reason", "TEXT"),
        ("currency", "VARCHAR(10) DEFAULT 'ZMW'"),
    ],
    "users": [
        ("last_login_at", "TIMESTAMP"),
        ("must_change_password", "BOOLEAN DEFAULT FALSE"),
    ],
    "subscriptions": [
        ("lipila_reference_id", "VARCHAR(100)"),
        ("lipila_transaction_id", "VARCHAR(100)"),
        ("payment_method", "VARCHAR(30) DEFAULT 'mobile_money'"),
        ("account_number", "VARCHAR(50)"),
        ("is_sandbox_simulated", "BOOLEAN DEFAULT FALSE"),
        ("reconciled_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
    ],
    "payments": [
        ("currency", "VARCHAR(10) DEFAULT 'ZMW'"),
        ("lipila_reference_id", "VARCHAR(100)"),
        ("lipila_transaction_id", "VARCHAR(100)"),
        ("payment_method", "VARCHAR(30) DEFAULT 'manual'"),
        ("account_number", "VARCHAR(50)"),
        ("narration", "VARCHAR(255)"),
        ("status", "VARCHAR(30) DEFAULT 'completed'"),
        ("is_sandbox_simulated", "BOOLEAN DEFAULT FALSE"),
        ("reconciled_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
    ],
    "teachers": [
        ("is_active", "BOOLEAN DEFAULT TRUE"),
        ("email", "VARCHAR(150)"),
    ],
    "students": [
        ("status", "VARCHAR(30) DEFAULT 'active'"),
        ("phone", "VARCHAR(30)"),
    ],
    "classes": [
        ("is_active", "BOOLEAN DEFAULT TRUE"),
        ("grade_level", "VARCHAR(50)"),
        ("academic_year", "VARCHAR(50)"),
        ("class_teacher_id", "INTEGER"),
    ],
    "subjects": [
        ("is_active", "BOOLEAN DEFAULT TRUE"),
        ("description", "TEXT"),
    ],
    "exams": [
        ("class_id", "INTEGER"),
        ("subject_id", "INTEGER"),
        ("start_time", "VARCHAR(10)"),
        ("end_time", "VARCHAR(10)"),
        ("venue", "VARCHAR(100)"),
        ("exam_type", "VARCHAR(50) DEFAULT 'Main'"),
        ("status", "VARCHAR(30) DEFAULT 'scheduled'"),
        ("start_date", "DATE"),
        ("end_date", "DATE"),
    ],
    "timetables": [
        ("room", "VARCHAR(50)"),
        ("term_id", "INTEGER"),
        ("is_active", "BOOLEAN DEFAULT TRUE"),
    ],
    "attendance": [
        ("recorded_by_id", "INTEGER"),
        ("updated_at", "TIMESTAMP"),
        ("remarks", "VARCHAR(255)"),
    ],
    "results": [
        ("status", "VARCHAR(20) DEFAULT 'draft'"),
        ("remarks", "VARCHAR(255)"),
        ("created_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
    ],
    "assignments": [
        ("assignment_date", "DATE"),
        ("attachment_path", "VARCHAR(300)"),
        ("attachment_name", "VARCHAR(255)"),
        ("attachment_type", "VARCHAR(100)"),
    ],
    "materials": [
        ("term_id", "INTEGER"),
        ("is_archived", "BOOLEAN DEFAULT FALSE"),
        ("file_size", "INTEGER"),
    ],
    "sms_settings": [
        ("provider", "VARCHAR(50) DEFAULT 'easysendsms'"),
    ],
    "sms_messages": [
        ("provider", "VARCHAR(50) DEFAULT 'easysendsms'"),
    ],
}


def ensure_schema_columns(db):
    """Add missing columns to existing tables safely without destructive operations."""
    try:
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        logger.error("Could not inspect database tables during schema verification: %s", exc)
        return

    for table_name, columns in REQUIRED_COLUMNS.items():
        if table_name not in existing_tables:
            continue

        try:
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        except Exception as exc:
            logger.warning("Could not inspect columns for table %s: %s", table_name, exc)
            continue

        for col_name, col_type in columns:
            if col_name not in existing_cols:
                stmt = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                try:
                    db.session.execute(text(stmt))
                    db.session.commit()
                    logger.info("Added missing column %s.%s", table_name, col_name)
                    existing_cols.add(col_name)
                except Exception as exc:
                    db.session.rollback()
                    logger.warning("Could not add column %s.%s: %s", table_name, col_name, exc)

    # Safe backfill for multi-day exams from existing single-date records
    if "exams" in existing_tables:
        try:
            db.session.execute(text("UPDATE exams SET start_date = date, end_date = date WHERE start_date IS NULL AND date IS NOT NULL"))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.debug("Could not backfill exam start/end dates: %s", exc)

    # Safe backfill for school currency
    if "schools" in existing_tables:
        try:
            db.session.execute(text("UPDATE schools SET currency = 'ZMW' WHERE currency IS NULL"))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.debug("Could not backfill school currency: %s", exc)

    # Safe backfill for historical results (preserve legacy results as published)
    if "results" in existing_tables:
        try:
            db.session.execute(text("UPDATE results SET status = 'published' WHERE status IS NULL"))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.debug("Could not backfill result status: %s", exc)

    # Keep alembic_version in sync if the table exists
    if "alembic_version" in existing_tables:
        try:
            db.session.execute(text("DELETE FROM alembic_version"))
            db.session.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0005_schools_currency_and_schema_sync')"))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.debug("Could not sync alembic_version: %s", exc)
