"""Add SMS role upgrade fields: School currency, Attendance remarks, and Result status & remarks.

Revision ID: 0002_sms_role_upgrade
Revises: 0001_lipila_schema_upgrade
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_sms_role_upgrade"
down_revision = "0001_lipila_schema_upgrade"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table_name not in insp.get_table_names():
        return False
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade():
    # 1. schools: currency
    if not _has_column("schools", "currency"):
        op.add_column("schools", sa.Column("currency", sa.String(length=10), server_default="ZMW", nullable=True))

    # 2. attendance: remarks
    if not _has_column("attendance", "remarks"):
        op.add_column("attendance", sa.Column("remarks", sa.String(length=255), nullable=True))

    # 3. results: status, remarks, created_at, updated_at
    # Future inserts must default to 'draft'; legacy records are preserved as 'published'.
    if not _has_column("results", "status"):
        op.add_column("results", sa.Column("status", sa.String(length=20), server_default="draft", nullable=False))
        # Backfill existing legacy records so historical results remain published
        op.execute("UPDATE results SET status = 'published' WHERE status IS NULL OR status = 'draft'")
    else:
        # Ensure default on existing column is set to 'draft'
        try:
            op.alter_column("results", "status", server_default="draft")
        except Exception:
            pass

    if not _has_column("results", "remarks"):
        op.add_column("results", sa.Column("remarks", sa.String(length=255), nullable=True))
    if not _has_column("results", "created_at"):
        op.add_column("results", sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True))
    if not _has_column("results", "updated_at"):
        op.add_column("results", sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True))


def downgrade():
    if _has_column("results", "updated_at"):
        op.drop_column("results", "updated_at")
    if _has_column("results", "created_at"):
        op.drop_column("results", "created_at")
    if _has_column("results", "remarks"):
        op.drop_column("results", "remarks")
    if _has_column("results", "status"):
        op.drop_column("results", "status")
    if _has_column("attendance", "remarks"):
        op.drop_column("attendance", "remarks")
    if _has_column("schools", "currency"):
        op.drop_column("schools", "currency")
