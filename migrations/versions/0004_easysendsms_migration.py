"""Migration for EasySendSMS provider integration and delivery report tracking.

Revision ID: 0004_easysendsms_migration
Revises: 0003_class_teacher_and_sms
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_easysendsms_migration"
down_revision = "0003_class_teacher_and_sms"
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
    # Add provider column to sms_settings
    if _has_table("sms_settings") and not _has_column("sms_settings", "provider"):
        op.add_column(
            "sms_settings",
            sa.Column("provider", sa.String(length=50), server_default="easysendsms", nullable=True),
        )

    # Add provider column to sms_messages
    if _has_table("sms_messages") and not _has_column("sms_messages", "provider"):
        op.add_column(
            "sms_messages",
            sa.Column("provider", sa.String(length=50), server_default="easysendsms", nullable=True),
        )


def downgrade():
    if _has_table("sms_messages") and _has_column("sms_messages", "provider"):
        op.drop_column("sms_messages", "provider")

    if _has_table("sms_settings") and _has_column("sms_settings", "provider"):
        op.drop_column("sms_settings", "provider")
