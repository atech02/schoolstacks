"""Add Lipila payment and reconciliation fields while preserving historical Stripe columns.

Revision ID: 0001_lipila_schema_upgrade
Revises: None
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_lipila_schema_upgrade"
down_revision = None
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if table_name not in insp.get_table_names():
        return False
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade():
    # 1. schools
    if not _has_column("schools", "lipila_customer_ref"):
        op.add_column("schools", sa.Column("lipila_customer_ref", sa.String(length=100), nullable=True))
    if not _has_column("schools", "lipila_subscription_ref"):
        op.add_column("schools", sa.Column("lipila_subscription_ref", sa.String(length=100), nullable=True))

    # 2. subscriptions
    for col_name, col_def in [
        ("lipila_reference_id", sa.Column("lipila_reference_id", sa.String(length=100), nullable=True)),
        ("lipila_transaction_id", sa.Column("lipila_transaction_id", sa.String(length=100), nullable=True)),
        ("payment_method", sa.Column("payment_method", sa.String(length=30), server_default="mobile_money", nullable=True)),
        ("account_number", sa.Column("account_number", sa.String(length=50), nullable=True)),
        ("is_sandbox_simulated", sa.Column("is_sandbox_simulated", sa.Boolean(), server_default=sa.text("0"), nullable=True)),
        ("reconciled_at", sa.Column("reconciled_at", sa.DateTime(), nullable=True)),
        ("updated_at", sa.Column("updated_at", sa.DateTime(), nullable=True)),
    ]:
        if not _has_column("subscriptions", col_name):
            op.add_column("subscriptions", col_def)

    # 3. payments
    for col_name, col_def in [
        ("currency", sa.Column("currency", sa.String(length=10), server_default="ZMW", nullable=True)),
        ("lipila_reference_id", sa.Column("lipila_reference_id", sa.String(length=100), nullable=True)),
        ("lipila_transaction_id", sa.Column("lipila_transaction_id", sa.String(length=100), nullable=True)),
        ("payment_method", sa.Column("payment_method", sa.String(length=30), server_default="manual", nullable=True)),
        ("account_number", sa.Column("account_number", sa.String(length=50), nullable=True)),
        ("narration", sa.Column("narration", sa.String(length=255), nullable=True)),
        ("status", sa.Column("status", sa.String(length=30), server_default="completed", nullable=True)),
        ("is_sandbox_simulated", sa.Column("is_sandbox_simulated", sa.Boolean(), server_default=sa.text("0"), nullable=True)),
        ("reconciled_at", sa.Column("reconciled_at", sa.DateTime(), nullable=True)),
        ("updated_at", sa.Column("updated_at", sa.DateTime(), nullable=True)),
    ]:
        if not _has_column("payments", col_name):
            op.add_column("payments", col_def)


def downgrade():
    with op.batch_alter_table("payments") as batch_op:
        for col in [
            "updated_at",
            "reconciled_at",
            "is_sandbox_simulated",
            "status",
            "narration",
            "account_number",
            "payment_method",
            "lipila_transaction_id",
            "lipila_reference_id",
            "currency",
        ]:
            if _has_column("payments", col):
                batch_op.drop_column(col)

    with op.batch_alter_table("subscriptions") as batch_op:
        for col in [
            "updated_at",
            "reconciled_at",
            "is_sandbox_simulated",
            "account_number",
            "payment_method",
            "lipila_transaction_id",
            "lipila_reference_id",
        ]:
            if _has_column("subscriptions", col):
                batch_op.drop_column(col)

    with op.batch_alter_table("schools") as batch_op:
        for col in ["lipila_subscription_ref", "lipila_customer_ref"]:
            if _has_column("schools", col):
                batch_op.drop_column(col)
