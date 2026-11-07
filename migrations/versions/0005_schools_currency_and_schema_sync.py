"""Add missing schools.currency, classes.class_teacher_id, attendance.remarks, and results status/remarks fields.

Revision ID: 0005_schools_currency_and_schema_sync
Revises: 0004_easysendsms_migration
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0005_schools_currency_and_schema_sync"
down_revision = "0004_easysendsms_migration"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table_name not in insp.get_table_names():
        return False
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade():
    # 1. schools: currency
    if _has_table("schools") and not _has_column("schools", "currency"):
        op.add_column("schools", sa.Column("currency", sa.String(length=10), server_default="ZMW", nullable=True))
        try:
            op.execute("UPDATE schools SET currency = 'ZMW' WHERE currency IS NULL")
        except Exception:
            pass

    # 2. classes: class_teacher_id
    if _has_table("classes") and not _has_column("classes", "class_teacher_id"):
        op.add_column("classes", sa.Column("class_teacher_id", sa.Integer(), nullable=True))

    # 3. attendance: remarks
    if _has_table("attendance") and not _has_column("attendance", "remarks"):
        op.add_column("attendance", sa.Column("remarks", sa.String(length=255), nullable=True))

    # 4. results: status, remarks, created_at, updated_at
    if _has_table("results") and not _has_column("results", "status"):
        op.add_column("results", sa.Column("status", sa.String(length=20), server_default="draft", nullable=False))
        try:
            op.execute("UPDATE results SET status = 'published' WHERE status IS NULL")
        except Exception:
            pass

    if _has_table("results") and not _has_column("results", "remarks"):
        op.add_column("results", sa.Column("remarks", sa.String(length=255), nullable=True))

    if _has_table("results") and not _has_column("results", "created_at"):
        op.add_column("results", sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True))

    if _has_table("results") and not _has_column("results", "updated_at"):
        op.add_column("results", sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True))


def downgrade():
    if _has_table("results") and _has_column("results", "updated_at"):
        op.drop_column("results", "updated_at")
    if _has_table("results") and _has_column("results", "created_at"):
        op.drop_column("results", "created_at")
    if _has_table("results") and _has_column("results", "remarks"):
        op.drop_column("results", "remarks")
    if _has_table("results") and _has_column("results", "status"):
        op.drop_column("results", "status")
    if _has_table("attendance") and _has_column("attendance", "remarks"):
        op.drop_column("attendance", "remarks")
    if _has_table("classes") and _has_column("classes", "class_teacher_id"):
        op.drop_column("classes", "class_teacher_id")
    if _has_table("schools") and _has_column("schools", "currency"):
        op.drop_column("schools", "currency")
