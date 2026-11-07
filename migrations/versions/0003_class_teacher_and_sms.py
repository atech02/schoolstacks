"""Add Class Teacher Allocation, Substitute Allocation, SMS.to, and Parent Communication tables.

Revision ID: 0003_class_teacher_and_sms
Revises: 0002_sms_role_upgrade
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_class_teacher_and_sms"
down_revision = "0002_sms_role_upgrade"
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
    # 1. class_teacher_allocations
    if not _has_table("class_teacher_allocations"):
        op.create_table(
            "class_teacher_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id"), nullable=False, index=True),
            sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False, index=True),
            sa.Column("academic_year", sa.String(length=50), nullable=False, index=True),
            sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_years.id"), nullable=True),
            sa.Column("section", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False, index=True),
            sa.Column("assigned_date", sa.Date(), nullable=True),
            sa.Column("ended_date", sa.Date(), nullable=True),
            sa.Column("previous_teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=True),
            sa.Column("assigned_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("override_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 2. substitute_allocations
    if not _has_table("substitute_allocations"):
        op.create_table(
            "substitute_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id"), nullable=False, index=True),
            sa.Column("primary_teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False),
            sa.Column("substitute_teacher_id", sa.Integer(), sa.ForeignKey("teachers.id"), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("authorized_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 3. sms_settings
    if not _has_table("sms_settings"):
        op.create_table(
            "sms_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), unique=True, nullable=False, index=True),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("sender_id", sa.String(length=30), nullable=True),
            sa.Column("fee_reminders_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("fee_reminder_days", sa.String(length=50), server_default="7,0,-7", nullable=False),
            sa.Column("fee_custom_message", sa.Text(), nullable=True),
            sa.Column("absenteeism_alerts_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("absenteeism_consecutive_threshold", sa.Integer(), server_default="2", nullable=False),
            sa.Column("absenteeism_urgent_threshold", sa.Integer(), server_default="3", nullable=False),
            sa.Column("absenteeism_intervention_threshold", sa.Integer(), server_default="5", nullable=False),
            sa.Column("absenteeism_window_days", sa.Integer(), server_default="30", nullable=False),
            sa.Column("absenteeism_custom_message", sa.Text(), nullable=True),
            sa.Column("enable_subject_attendance", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("attendance_correction_window_hours", sa.Integer(), server_default="24", nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 4. sms_messages
    if not _has_table("sms_messages"):
        op.create_table(
            "sms_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("recipient_phone", sa.String(length=30), nullable=False),
            sa.Column("recipient_name", sa.String(length=100), nullable=True),
            sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=True),
            sa.Column("message_body", sa.Text(), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False, index=True),
            sa.Column("status", sa.String(length=30), server_default="queued", nullable=False, index=True),
            sa.Column("provider_message_id", sa.String(length=100), nullable=True, index=True),
            sa.Column("cost", sa.Float(), server_default="0.0", nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("delivered_at", sa.DateTime(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=100), unique=True, nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True, index=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 5. sms_delivery_events
    if not _has_table("sms_delivery_events"):
        op.create_table(
            "sms_delivery_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sms_message_id", sa.Integer(), sa.ForeignKey("sms_messages.id"), nullable=True, index=True),
            sa.Column("provider_message_id", sa.String(length=100), nullable=True, index=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("raw_payload", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 6. parent_communication_logs
    if not _has_table("parent_communication_logs"):
        op.create_table(
            "parent_communication_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False, index=True),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("parents.id"), nullable=True),
            sa.Column("staff_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("channel", sa.String(length=20), server_default="phone", nullable=False),
            sa.Column("phone_number", sa.String(length=30), nullable=True),
            sa.Column("reason", sa.String(length=100), nullable=False),
            sa.Column("outcome", sa.String(length=100), nullable=False),
            sa.Column("follow_up_date", sa.Date(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 7. absenteeism_interventions
    if not _has_table("absenteeism_interventions"):
        op.create_table(
            "absenteeism_interventions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False, index=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id"), nullable=False, index=True),
            sa.Column("consecutive_days", sa.Integer(), server_default="0", nullable=False),
            sa.Column("cumulative_days", sa.Integer(), server_default="0", nullable=False),
            sa.Column("threshold_level", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=30), server_default="open", nullable=False, index=True),
            sa.Column("flagged_date", sa.Date(), nullable=True),
            sa.Column("last_alert_sent_at", sa.DateTime(), nullable=True),
            sa.Column("action_taken", sa.Text(), nullable=True),
            sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        )

    # 8. subject_attendance
    if not _has_table("subject_attendance"):
        op.create_table(
            "subject_attendance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id"), nullable=False, index=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id"), nullable=False),
            sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id"), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("period", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("remarks", sa.String(length=255), nullable=True),
            sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.UniqueConstraint("school_id", "student_id", "subject_id", "date", name="uq_subject_attendance"),
        )


def downgrade():
    if _has_table("subject_attendance"):
        op.drop_table("subject_attendance")
    if _has_table("absenteeism_interventions"):
        op.drop_table("absenteeism_interventions")
    if _has_table("parent_communication_logs"):
        op.drop_table("parent_communication_logs")
    if _has_table("sms_delivery_events"):
        op.drop_table("sms_delivery_events")
    if _has_table("sms_messages"):
        op.drop_table("sms_messages")
    if _has_table("sms_settings"):
        op.drop_table("sms_settings")
    if _has_table("substitute_allocations"):
        op.drop_table("substitute_allocations")
    if _has_table("class_teacher_allocations"):
        op.drop_table("class_teacher_allocations")
