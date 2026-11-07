"""
utils.py — Helpers, decorators, multi-tenant enforcement, and plan enforcement
"""
import os
import hmac
import json
import secrets
from datetime import datetime
from functools import wraps
from flask import redirect, url_for, flash, g, current_app, abort
from flask_login import current_user
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def get_current_school_id(required=True):
    """
    Return the authoritative school_id for the current request.
    Never trusts client-supplied school_id.
    """
    if current_user.is_authenticated and not current_user.is_superadmin:
        if current_user.school_id:
            return current_user.school_id
    school = getattr(g, "school", None)
    if school:
        return school.id
    if required:
        abort(403)
    return None


# ── Grade / Balance helpers ────────────────────────────────────────
def calculate_grade(marks):
    if marks is None:
        return "N/A"
    if marks >= 80:
        return "A"
    if marks >= 70:
        return "B"
    if marks >= 60:
        return "C"
    if marks >= 50:
        return "D"
    return "F"


def calculate_balance(student_id, term_id, school_id=None):
    """
    Calculate outstanding fee balance for a student in a specific term and school.
    Only completed (or legacy null-status) payments reduce the balance.
    """
    from models import Student, FeeStructure, Payment

    if school_id is None:
        school_id = get_current_school_id(required=True)

    student = Student.query.filter_by(id=student_id, school_id=school_id).first()
    if not student:
        return 0.0

    fee = FeeStructure.query.filter_by(
        school_id=school_id, class_id=student.class_id, term_id=term_id
    ).first()
    if not fee:
        return 0.0

    total_paid = (
        db.session.query(db.func.sum(Payment.amount_paid))
        .filter(
            Payment.school_id == school_id,
            Payment.student_id == student_id,
            Payment.term_id == term_id,
            db.or_(Payment.status == "completed", Payment.status.is_(None)),
        )
        .scalar()
        or 0.0
    )
    return round(float(fee.amount) - float(total_paid), 2)


def generate_unique_reference(school_id=None):
    """Generate a unique, collision-resistant receipt reference (RCT-xxxxx)."""
    from models import Payment

    if school_id is None:
        school_id = get_current_school_id(required=False)

    for _ in range(50):
        digits = secrets.randbelow(90000) + 10000
        ref = f"RCT-{digits}"
        q = Payment.query.filter_by(reference=ref)
        if school_id is not None:
            q = q.filter_by(school_id=school_id)
        if not q.first():
            return ref

    # Fallback with hex suffix if 5-digit space is dense
    return f"RCT-{secrets.token_hex(4).upper()}"


def allowed_file(filename):
    exts = current_app.config.get("ALLOWED_EXTENSIONS", set())
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def send_notification(user_id, school_id_or_msg, message=None, notif_type=None):
    """
    Queue a notification (caller must commit).
    Supports both 4-arg (user_id, school_id, message, notif_type)
    and legacy 3-arg (user_id, message, notif_type) call signatures.
    """
    from models import Notification

    if notif_type is None and message is not None:
        # Called as send_notification(user_id, message, notif_type)
        notif_type = message
        message = school_id_or_msg
        school_id = get_current_school_id(required=True)
    else:
        school_id = school_id_or_msg

    n = Notification(
        user_id=user_id,
        school_id=school_id,
        message=message,
        type=notif_type,
    )
    db.session.add(n)


def check_fee_reminders():
    """Iterate active schools and create fee reminder notifications for students with balances."""
    from models import School, Student, User, Term

    for school in School.query.filter_by(is_active=True).all():
        students = Student.query.filter_by(school_id=school.id).all()
        terms = Term.query.filter_by(school_id=school.id, is_active=True).all()
        for student in students:
            user = User.query.filter_by(
                school_id=school.id, username=student.admission_no
            ).first()
            if not user:
                continue
            for term in terms:
                balance = calculate_balance(student.id, term.id, school.id)
                if balance > 0:
                    send_notification(
                        user.id,
                        school.id,
                        f"Outstanding balance of K{balance:.2f} for {term.name}",
                        "fee",
                    )
    db.session.commit()


# ── Email helpers ─────────────────────────────────────────────────
def send_verification_email(user):
    """Send email verification link."""
    from extensions import mail
    from flask_mail import Message
    from itsdangerous import URLSafeTimedSerializer

    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    token = s.dumps(user.email, salt="email-verify")
    link = url_for("onboarding.verify_email", token=token, _external=True)
    msg = Message(
        subject="Verify your EduManage account",
        recipients=[user.email],
        html=f"""
        <h2>Welcome to EduManage!</h2>
        <p>Click the link below to verify your email address:</p>
        <a href="{link}" style="background:#0f1f3d;color:#fff;padding:12px 24px;
        border-radius:8px;text-decoration:none;font-weight:bold;">
        Verify Email
        </a>
        <p>This link expires in 24 hours.</p>
        """,
    )
    mail.send(msg)


def verify_email_token(token, max_age=86400):
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = s.loads(token, salt="email-verify", max_age=max_age)
        return email
    except (SignatureExpired, BadSignature):
        return None


# ── Plan limit enforcement ─────────────────────────────────────────
def check_plan_limit(resource: str):
    """
    Check whether the current school has hit its plan limit.
    resource: 'students' | 'teachers'
    Returns True if allowed, False if at limit.
    """
    from models import Student, Teacher, School

    school_id = get_current_school_id(required=False)
    if not school_id:
        return True
    school = db.session.get(School, school_id)
    if not school:
        return True

    limits = current_app.config["PLAN_LIMITS"]
    plan_limits = limits.get(school.plan, limits["free"])
    limit = plan_limits.get(resource, 0)

    if resource == "students":
        count = Student.query.filter_by(school_id=school.id).count()
    elif resource == "teachers":
        count = Teacher.query.filter_by(school_id=school.id).count()
    else:
        return True

    return count < limit


def plan_feature_required(min_plan: str):
    """
    Decorator: blocks a route if the school's plan is below min_plan.
    Order: free < starter < growth < enterprise
    """
    plan_order = ["free", "starter", "growth", "enterprise"]

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from models import School

            school = getattr(g, "school", None)
            if not school and current_user.is_authenticated and current_user.school_id:
                school = db.session.get(School, current_user.school_id)
            if not school:
                abort(403)

            current_idx = plan_order.index(school.plan) if school.plan in plan_order else 0
            required_idx = plan_order.index(min_plan) if min_plan in plan_order else 0

            if current_idx < required_idx:
                flash(f"This feature requires the {min_plan.title()} plan or higher.", "warning")
                return redirect(url_for("billing.plans"))

            return f(*args, **kwargs)

        return wrapper

    return decorator


# ── Role decorators ───────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Admin access required.", "danger")
            return redirect(url_for("auth.login"))
        if current_user.role not in ("admin", "superadmin"):
            abort(403)
        if current_user.role == "admin" and not current_user.school_id:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Teacher access required.", "danger")
            return redirect(url_for("auth.login"))
        if current_user.role != "teacher" or not current_user.school_id:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Student access required.", "danger")
            return redirect(url_for("auth.login"))
        if current_user.role != "student" or not current_user.school_id:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def parent_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Parent access required.", "danger")
            return redirect(url_for("auth.login"))
        if current_user.role != "parent" or not current_user.school_id:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)

    return decorated


def record_activity(
    category: str,
    event_type: str,
    description: str,
    *,
    school_id: int | None = None,
    actor_user=None,
    actor_username: str | None = None,
    actor_role: str | None = None,
    status: str = "success",
    target_type: str | None = None,
    target_id: str | int | None = None,
    metadata: dict | None = None,
    commit: bool = False,
):
    """
    Record a structured audit/activity event in activity_logs and update
    the target school's last_activity_at timestamp.
    """
    import json
    from models import ActivityLog, School, utc_now

    now = utc_now()
    user_obj = actor_user
    if user_obj is None and current_user and getattr(current_user, "is_authenticated", False):
        user_obj = current_user

    resolved_user_id = getattr(user_obj, "id", None) if user_obj else None
    resolved_username = actor_username or (getattr(user_obj, "username", None) if user_obj else "system")
    resolved_role = actor_role or (getattr(user_obj, "role", None) if user_obj else "system")

    if school_id is None and user_obj and getattr(user_obj, "school_id", None):
        school_id = user_obj.school_id

    entry = ActivityLog(
        school_id=school_id,
        actor_user_id=resolved_user_id,
        actor_username=resolved_username,
        actor_role=resolved_role,
        category=category,
        event_type=event_type,
        status=status,
        description=description,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        metadata_json=json.dumps(metadata) if metadata else None,
        created_at=now,
    )
    db.session.add(entry)

    if school_id is not None:
        school = db.session.get(School, school_id)
        if school:
            school.last_activity_at = now

    if commit:
        db.session.commit()

    return entry


def find_user_for_login(identifier: str, school_subdomain: str | None = None, target_school=None):
    """
    Look up a user attempting to sign in by username OR email address.
    Supports case-insensitive matching for usernames, emails, and the platform superadmin.

    Resolution order:
    1. Superadmin Check (by username 'superadmin' OR by superadmin email):
       Superadmin is a platform-wide role (school_id=None). If identifier matches 'superadmin'
       or any registered superadmin email, or the configured SUPERADMIN_EMAIL env variable,
       resolve to the platform superadmin regardless of whether a school is selected in the UI.
    2. School-scoped lookup:
       If target_school or school_subdomain is specified, look up within that school by
       username (case-insensitive) or email (case-insensitive).
    3. Single-school convenience fallback:
       If no school was specified and only 1 active school exists in the system, search that school.
    4. Global fallback across users:
       If no school was specified and no user was found yet, search all users by email or username.
    """
    from models import User, School

    if not identifier:
        return None

    clean_id = identifier.strip()
    id_lower = clean_id.lower()

    # 1. Platform Superadmin resolution (by username 'superadmin' OR by superadmin email)
    sa_email_env = (
        os.environ.get("SUPERADMIN_EMAIL")
        or (current_app.config.get("SUPERADMIN_EMAIL") if current_app else "")
        or ""
    ).strip().lower()

    if id_lower == "superadmin" or (sa_email_env and id_lower == sa_email_env):
        sa = User.query.filter_by(role="superadmin").first()
        if sa:
            return sa

    # Check if this identifier matches any existing superadmin's email directly
    sa_by_email = User.query.filter(
        User.role == "superadmin",
        func.lower(User.email) == id_lower
    ).first()
    if sa_by_email:
        return sa_by_email

    # Resolve target school
    resolved_school = target_school
    if not resolved_school and school_subdomain:
        clean_sub = school_subdomain.strip().lower()
        resolved_school = School.query.filter_by(subdomain=clean_sub, is_active=True).first()

    # 2. School-scoped lookup (username or email case-insensitive)
    if resolved_school:
        user = User.query.filter(
            User.school_id == resolved_school.id,
            (func.lower(User.username) == id_lower) | (func.lower(User.email) == id_lower)
        ).first()
        if user:
            return user

    # 3. Single-school convenience fallback
    if not resolved_school:
        active_schools = School.query.filter_by(is_active=True).all()
        if len(active_schools) == 1:
            user = User.query.filter(
                User.school_id == active_schools[0].id,
                (func.lower(User.username) == id_lower) | (func.lower(User.email) == id_lower)
            ).first()
            if user:
                return user

    # 4. Global fallback across users (by email or username)
    user = User.query.filter(
        (func.lower(User.username) == id_lower) | (func.lower(User.email) == id_lower)
    ).first()
    return user


def handle_superadmin_recovery(data: dict | None = None, header_token: str | None = None) -> tuple[dict, int]:
    """
    Secure administrative recovery for the Platform Superadmin account.
    Requires server-side SUPERADMIN_RECOVERY_TOKEN in environment variables.

    Security & Idempotency:
    - Returns 403 Forbidden if SUPERADMIN_RECOVERY_TOKEN is not configured on the server.
    - Uses constant-time hmac.compare_digest to prevent timing attacks.
    - Updates or provisions the Superadmin account using server environment credentials
      (SUPERADMIN_PASSWORD or ADMIN_PASSWORD, and SUPERADMIN_EMAIL) or authorized payload data.
    - Password is encrypted using werkzeug generate_password_hash; never logged or returned in plain text.
    - Enforces must_change_password=True.
    - Emits a security audit record.
    """
    from models import User

    configured_token = (
        os.environ.get("SUPERADMIN_RECOVERY_TOKEN")
        or (current_app.config.get("SUPERADMIN_RECOVERY_TOKEN") if current_app else "")
        or ""
    ).strip()

    if not configured_token:
        return {
            "error": "Superadmin recovery is disabled. Configure SUPERADMIN_RECOVERY_TOKEN in server environment variables to enable recovery."
        }, 403

    payload = data or {}
    provided_token = (header_token or payload.get("recovery_token") or "").strip()

    if not provided_token or not hmac.compare_digest(provided_token, configured_token):
        record_activity(
            "security",
            "superadmin_recovery_failed",
            "Unauthorized attempt to invoke superadmin recovery endpoint (invalid or missing token).",
            status="failed",
            commit=True,
        )
        return {"error": "Invalid recovery token."}, 401

    new_password = (
        payload.get("new_password")
        or os.environ.get("SUPERADMIN_PASSWORD")
        or os.environ.get("ADMIN_PASSWORD")
    )
    if not new_password:
        return {
            "error": "No new password provided in payload, and neither SUPERADMIN_PASSWORD nor ADMIN_PASSWORD is set in server environment."
        }, 400

    target_email = (
        payload.get("email")
        or os.environ.get("SUPERADMIN_EMAIL")
        or (current_app.config.get("SUPERADMIN_EMAIL") if current_app else None)
        or "superadmin@edumanage.zm"
    ).strip().lower()

    # Locate existing superadmin
    sa = User.query.filter_by(role="superadmin").first()
    if not sa:
        sa = User.query.filter(func.lower(User.email) == target_email).first()

    if not sa:
        sa = User(
            school_id=None,
            username="superadmin",
            email=target_email,
            password_hash=generate_password_hash(new_password),
            role="superadmin",
            is_verified=True,
            must_change_password=True,
        )
        db.session.add(sa)
    else:
        sa.username = "superadmin"
        sa.email = target_email
        sa.password_hash = generate_password_hash(new_password)
        sa.is_verified = True
        sa.must_change_password = True

    db.session.commit()

    record_activity(
        "security",
        "superadmin_password_recovered",
        f"Superadmin account credentials securely recovered for '{target_email}'.",
        status="warning",
        commit=True,
    )

    return {
        "message": "Superadmin credentials recovered successfully.",
        "username": sa.username,
        "email": sa.email,
        "must_change_password": True,
    }, 200

