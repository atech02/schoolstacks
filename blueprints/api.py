"""
blueprints/api.py — Comprehensive JSON API layer for the React + TypeScript frontend.
Preserves all Flask business logic, SQLAlchemy models, multi-tenant school isolation,
role/ownership authorization, and Lipila payment workflows.
"""
import os
import random
import datetime
from flask import Blueprint, jsonify, request, current_app, session, g, abort, send_file
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from extensions import db, csrf
from models import (
    School,
    Subscription,
    User,
    Student,
    Teacher,
    Parent,
    ParentStudent,
    SchoolClass,
    Subject,
    TeacherAssignment,
    Term,
    Exam,
    Result,
    FeeStructure,
    Payment,
    Attendance,
    Timetable,
    Announcement,
    Notification,
    Material,
    Assignment,
    Submission,
    ActivityLog,
    utc_now,
)
from utils import (
    get_current_school_id,
    calculate_balance,
    calculate_grade,
    send_notification,
    generate_unique_reference,
    allowed_file,
    check_plan_limit,
    record_activity,
)
from services.lipila import LipilaClient, LipilaError, normalize_zambia_phone
from blueprints.billing import (
    _authorize_student_fee_access,
    _settle_subscription,
    _settle_fee_payment,
)
import re
from blueprints.onboarding import RESERVED

def _clean_subdomain(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9\-]", "", (raw or "").strip().lower()).strip("-")
    if slug in RESERVED:
        return ""
    return slug


def validate_and_normalize_phone(raw_phone: str, required: bool = True) -> str:
    r"""
    Validate and normalize Zambian phone numbers.
    Accepts numbers with spaces, hyphens, dots, or parentheses (e.g. '097 712 3456', '+260 97 712 3456').
    Strips harmless whitespace/characters and validates against ^(\+?260|0)[79]\d{8}$.
    Returns standardized format (e.g. 0977123456).
    """
    if raw_phone is None:
        raw_phone = ""
    cleaned = re.sub(r"[\s\-\.\(\)]+", "", str(raw_phone).strip())
    if not cleaned:
        if required:
            raise ValueError("Phone number is required.")
        return ""

    # Validate against Zambian mobile phone pattern
    if re.match(r"^(\+?260|0)[79]\d{8}$", cleaned):
        if cleaned.startswith("+260"):
            return "0" + cleaned[4:]
        return cleaned
    elif re.match(r"^260[79]\d{8}$", cleaned):
        return "0" + cleaned[3:]
    elif re.match(r"^[79]\d{8}$", cleaned):
        return "0" + cleaned

    raise ValueError("Invalid phone number. Please enter the number without spaces, for example 0977123456.")


api = Blueprint("api", __name__, url_prefix="/api")

# Exempt JSON API routes from HTML form CSRF redirect; session + same-origin + role checks apply
csrf.exempt(api)


def _serialize_school(school: School | None):
    if not school:
        return None
    return {
        "id": school.id,
        "name": school.name,
        "subdomain": school.subdomain,
        "email": school.email,
        "phone": school.phone,
        "address": school.address,
        "plan": school.plan,
        "billing_cycle": school.billing_cycle,
        "is_active": school.is_active,
        "on_trial": school.is_on_trial(),
        "subscription_active": school.subscription_active(),
        "trial_ends_at": school.trial_ends_at.isoformat() if school.trial_ends_at else None,
        "subscription_ends_at": school.subscription_ends_at.isoformat() if school.subscription_ends_at else None,
    }


def _serialize_user(user: User | None):
    if not user or not user.is_authenticated:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "school_id": user.school_id,
        "student_id": user.student_id,
        "is_verified": user.is_verified,
        "must_change_password": bool(getattr(user, "must_change_password", False)),
    }


def _require_role(*roles):
    if not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401
    if current_user.role not in roles:
        return jsonify({"error": "Insufficient permissions for this resource"}), 403
    return None


def get_teacher_assigned_classes_and_subjects(teacher_id: int | None, school_id: int):
    """
    Computes classes and subjects assigned to a teacher via:
    1. TeacherAssignment records
    2. Timetable records (active entries)
    3. SchoolClass records where class_teacher_id == teacher_id
    Returns:
      (assigned_class_ids: set[int], assigned_subject_ids: set[int], class_subject_map: dict[int, list[int]])
    """
    assigned_class_ids = set()
    assigned_subject_ids = set()
    class_subject_map = {}

    if not teacher_id:
        return assigned_class_ids, assigned_subject_ids, class_subject_map

    # From TeacherAssignment
    tas = TeacherAssignment.query.filter_by(school_id=school_id, teacher_id=teacher_id).all()
    for ta in tas:
        if ta.class_id:
            assigned_class_ids.add(ta.class_id)
            class_subject_map.setdefault(ta.class_id, set())
            if ta.subject_id:
                assigned_subject_ids.add(ta.subject_id)
                class_subject_map[ta.class_id].add(ta.subject_id)

    # From Timetable
    timetables = Timetable.query.filter_by(school_id=school_id, teacher_id=teacher_id, is_active=True).all()
    for tt in timetables:
        if tt.class_id:
            assigned_class_ids.add(tt.class_id)
            class_subject_map.setdefault(tt.class_id, set())
            if tt.subject_id:
                assigned_subject_ids.add(tt.subject_id)
                class_subject_map[tt.class_id].add(tt.subject_id)

    # From SchoolClass (home room / class teacher)
    class_teacher_classes = SchoolClass.query.filter_by(school_id=school_id, class_teacher_id=teacher_id).all()
    for sc in class_teacher_classes:
        assigned_class_ids.add(sc.id)
        class_subject_map.setdefault(sc.id, set())

    converted_map = {cid: sorted(list(sids)) for cid, sids in class_subject_map.items()}
    return assigned_class_ids, assigned_subject_ids, converted_map


@api.route("/bootstrap", methods=["GET"])
def bootstrap():
    schools = School.query.filter_by(is_active=True).order_by(School.name.asc()).all()
    current_school = getattr(g, "school", None)
    if not current_school and current_user.is_authenticated and current_user.school_id:
        current_school = db.session.get(School, current_user.school_id)

    unread_count = 0
    if current_user.is_authenticated and current_user.school_id:
        unread_count = Notification.query.filter_by(
            school_id=current_user.school_id, user_id=current_user.id, is_read=False
        ).count()

    client = LipilaClient()
    return jsonify({
        "authenticated": current_user.is_authenticated,
        "csrf_token": generate_csrf(),
        "user": _serialize_user(current_user),
        "school": _serialize_school(current_school),
        "schools": [
            {"id": s.id, "name": s.name, "subdomain": s.subdomain}
            for s in schools
        ],
        "unread_notifications": unread_count,
        "pricing": {
            "prices": current_app.config["PLAN_PRICES"],
            "limits": current_app.config["PLAN_LIMITS"],
            "features": current_app.config["PLAN_FEATURES"],
            "simulator_enabled": client.simulator_enabled,
        },
    })


# ══════════════════════════════════════════════════════════════════
#  AUTHENTICATION & ONBOARDING
# ══════════════════════════════════════════════════════════════════

@api.route("/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    school_subdomain = (data.get("school_subdomain") or "").strip().lower()

    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400

    schools = School.query.filter_by(is_active=True).order_by(School.name.asc()).all()
    target_school = getattr(g, "school", None)
    if school_subdomain:
        target_school = School.query.filter_by(
            subdomain=school_subdomain
        ).first()

    user = None
    if target_school:
        user = User.query.filter_by(
            school_id=target_school.id, username=username
        ).first()

    if not user and username == "superadmin":
        user = User.query.filter_by(username="superadmin", role="superadmin").first()

    if not user and not target_school and len(schools) == 1:
        target_school = schools[0]
        user = User.query.filter_by(
            school_id=target_school.id, username=username
        ).first()

    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid username, school selection, or password."}), 401

    user_school = None
    if user.school_id:
        user_school = db.session.get(School, user.school_id)
        if not user_school or not user_school.is_active:
            record_activity(
                "auth",
                "login_blocked_suspended",
                f"Blocked login attempt for {user.role} '{user.username}' while school is suspended.",
                school_id=user.school_id,
                actor_user=user,
                status="warning",
                commit=True,
            )
            return jsonify({
                "error": "This school account is currently suspended. Please contact platform support.",
                "school_suspended": True,
            }), 403
        session["selected_school_subdomain"] = user_school.subdomain
        session["school_id"] = user_school.id

    if not user.is_verified and user.role == "admin":
        return jsonify({"error": "Please verify your email address before logging in."}), 403

    user.last_login_at = utc_now()
    record_activity(
        "auth",
        "admin_login" if user.role == "admin" else "user_login",
        f"{user.role.title()} '{user.username}' signed in.",
        school_id=user.school_id,
        actor_user=user,
        status="success",
        commit=True,
    )
    login_user(user)
    return jsonify({
        "message": "Signed in successfully.",
        "user": _serialize_user(user),
        "school": _serialize_school(user_school),
    })


@api.route("/auth/logout", methods=["POST"])
def api_logout():
    logout_user()
    return jsonify({"message": "Signed out successfully."})


@api.route("/auth/change-password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json(silent=True) or request.form
    current_pw = data.get("current_password") or ""
    new_pw = data.get("new_password") or ""
    confirm_pw = data.get("confirm_password") or ""

    if not all([current_pw, new_pw, confirm_pw]):
        return jsonify({"error": "All password fields are required."}), 400
    if not check_password_hash(current_user.password_hash, current_pw):
        return jsonify({"error": "Current password is incorrect."}), 400
    if new_pw != confirm_pw:
        return jsonify({"error": "New passwords do not match."}), 400
    if len(new_pw) < 8:
        return jsonify({"error": "New password must be at least 8 characters."}), 400

    current_user.set_password(new_pw)
    current_user.must_change_password = False
    db.session.commit()
    return jsonify({"message": "Password changed successfully."})


@api.route("/onboarding/register", methods=["POST"])
def api_register_school():
    data = request.get_json(silent=True) or request.form
    school_name = (data.get("school_name") or "").strip()
    subdomain = _clean_subdomain(data.get("subdomain") or "")
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    confirm_pw = data.get("confirm_password") or ""

    errors = []
    if not school_name or len(school_name) < 3:
        errors.append("School name must be at least 3 characters.")
    if not subdomain:
        errors.append("Subdomain must be 3-50 lowercase letters, numbers, or hyphens.")
    elif School.query.filter_by(subdomain=subdomain).first():
        errors.append(f"'{subdomain}' is already taken. Please choose another identifier.")
    if not email or "@" not in email:
        errors.append("A valid admin email is required.")
    elif School.query.filter_by(email=email).first():
        errors.append("An account with this email already exists.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif password != confirm_pw:
        errors.append("Passwords do not match.")

    if errors:
        return jsonify({"error": " ".join(errors), "errors": errors}), 400

    school = School(
        name=school_name,
        subdomain=subdomain,
        email=email,
        phone=phone or None,
        plan="free",
        trial_ends_at=utc_now() + datetime.timedelta(days=14),
    )
    db.session.add(school)
    db.session.flush()

    admin_user = User(
        school_id=school.id,
        username="admin",
        email=email,
        password_hash=generate_password_hash(password),
        role="admin",
        is_verified=True,
        last_login_at=utc_now(),
    )
    db.session.add(admin_user)
    db.session.flush()
    record_activity(
        "onboarding",
        "school_registered",
        f"School '{school.name}' ({school.subdomain}) registered with administrator '{admin_user.username}'.",
        school_id=school.id,
        actor_user=admin_user,
        target_type="school",
        target_id=school.id,
        commit=False,
    )
    db.session.commit()

    session["school_id"] = school.id
    session["selected_school_subdomain"] = school.subdomain
    login_user(admin_user)

    return jsonify({
        "message": f"Welcome! '{school.name}' is registered with a 14-day free trial.",
        "user": _serialize_user(admin_user),
        "school": _serialize_school(school),
    }), 201


# ══════════════════════════════════════════════════════════════════
#  SCHOOL ADMIN PORTAL
# ══════════════════════════════════════════════════════════════════

@api.route("/admin/overview", methods=["GET"])
@login_required
def api_admin_overview():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()

    classes = SchoolClass.query.filter_by(school_id=school_id).order_by(SchoolClass.name.asc()).all()
    subjects = Subject.query.filter_by(school_id=school_id).order_by(Subject.name.asc()).all()
    terms = Term.query.filter_by(school_id=school_id).order_by(Term.start_date.desc()).all()
    exams = Exam.query.filter_by(school_id=school_id).all()
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    students = Student.query.filter_by(school_id=school_id).all()
    fees = FeeStructure.query.filter_by(school_id=school_id).all()
    payments = (
        Payment.query.filter_by(school_id=school_id)
        .order_by(Payment.payment_date.desc())
        .limit(25)
        .all()
    )
    announcements = (
        Announcement.query.filter_by(school_id=school_id)
        .order_by(Announcement.created_at.desc())
        .limit(20)
        .all()
    )
    timetables = Timetable.query.filter_by(school_id=school_id).all()

    total_collected = (
        db.session.query(func.coalesce(func.sum(Payment.amount_paid), 0.0))
        .filter(Payment.school_id == school_id, Payment.status == "completed")
        .scalar()
        or 0.0
    )

    subject_stats = []
    for subj in subjects:
        res_list = Result.query.filter_by(school_id=school_id, subject_id=subj.id).all()
        avg = round(sum(r.marks for r in res_list) / len(res_list), 1) if res_list else 0.0
        subject_stats.append({
            "id": subj.id,
            "name": subj.name,
            "code": subj.code,
            "description": subj.description or "",
            "is_active": subj.is_active if subj.is_active is not None else True,
            "average": avg,
            "count": len(res_list),
        })

    all_results = Result.query.filter_by(school_id=school_id).all()
    pass_count = sum(1 for r in all_results if r.marks >= 50)
    fail_count = sum(1 for r in all_results if r.marks < 50)

    attendance_all = Attendance.query.filter_by(school_id=school_id).all()
    present_count = sum(1 for a in attendance_all if a.status == "Present")
    absent_count = sum(1 for a in attendance_all if a.status == "Absent")

    active_term = terms[0] if terms else None
    class_map = {c.id: c.name for c in classes}
    term_map = {t.id: t.name for t in terms}
    subj_map = {s.id: s.name for s in subjects}
    teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
    student_map = {s.id: f"{s.first_name} {s.last_name} ({s.admission_no})" for s in students}
    parent_map = {p.id: p.phone for p in Parent.query.filter_by(school_id=school_id).all()}

    return jsonify({
        "metrics": {
            "total_students": len(students),
            "total_teachers": len(teachers),
            "total_parents": Parent.query.filter_by(school_id=school_id).count(),
            "total_classes": len(classes),
            "total_subjects": len(subjects),
            "total_collected_zmw": round(float(total_collected), 2),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "present_count": present_count,
            "absent_count": absent_count,
        },
        "classes": [
            {
                "id": c.id,
                "name": c.name,
                "capacity": c.capacity,
                "grade_level": c.grade_level or "",
                "academic_year": c.academic_year or "",
                "class_teacher_id": c.class_teacher_id,
                "class_teacher_name": teacher_map.get(c.class_teacher_id, "—"),
                "is_active": c.is_active if c.is_active is not None else True,
                "student_count": sum(1 for s in students if s.class_id == c.id),
            }
            for c in classes
        ],
        "subjects": subject_stats,
        "terms": [
            {
                "id": t.id,
                "name": t.name,
                "start_date": t.start_date.isoformat() if t.start_date else None,
                "end_date": t.end_date.isoformat() if t.end_date else None,
                "is_active": t.is_active if t.is_active is not None else True,
            }
            for t in terms
        ],
        "exams": [
            {
                "id": e.id,
                "name": e.name,
                "term_id": e.term_id,
                "term_name": term_map.get(e.term_id, "—"),
                "class_id": e.class_id,
                "class_name": class_map.get(e.class_id, "All / Unspecified"),
                "subject_id": e.subject_id,
                "subject_name": subj_map.get(e.subject_id, "General"),
                "date": e.date.isoformat() if e.date else (e.start_date.isoformat() if e.start_date else None),
                "start_date": e.start_date.isoformat() if e.start_date else (e.date.isoformat() if e.date else None),
                "end_date": e.end_date.isoformat() if e.end_date else (e.start_date.isoformat() if e.start_date else (e.date.isoformat() if e.date else None)),
                "start_time": e.start_time or "",
                "end_time": e.end_time or "",
                "venue": e.venue or "",
                "exam_type": e.exam_type or "Main",
                "status": e.status or "scheduled",
            }
            for e in exams
        ],
        "students": [
            {
                "id": s.id,
                "admission_no": s.admission_no,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "gender": s.gender,
                "phone": s.phone or "",
                "status": s.status or "active",
                "class_id": s.class_id,
                "class_name": class_map.get(s.class_id, "Unassigned"),
                "parent_phone": parent_map.get(s.parent_id, "") or "",
                "balance": calculate_balance(s.id, active_term.id, school_id) if active_term else 0.0,
            }
            for s in students
        ],
        "teachers": [
            {
                "id": t.id,
                "staff_no": t.staff_no,
                "first_name": t.first_name,
                "last_name": t.last_name,
                "email": t.email or "",
                "phone": t.phone or "",
                "subject_specialization": t.subject_specialization or "General",
                "is_active": t.is_active if t.is_active is not None else True,
            }
            for t in teachers
        ],
        "fees": [
            {
                "id": f.id,
                "class_id": f.class_id,
                "class_name": class_map.get(f.class_id, "—"),
                "term_id": f.term_id,
                "term_name": term_map.get(f.term_id, "—"),
                "amount": f.amount,
            }
            for f in fees
        ],
        "payments": [
            {
                "id": p.id,
                "student_id": p.student_id,
                "student_name": student_map.get(p.student_id, "—"),
                "term_id": p.term_id,
                "term_name": term_map.get(p.term_id, "—"),
                "amount_paid": p.amount_paid,
                "currency": p.currency or "ZMW",
                "reference": p.reference,
                "lipila_reference_id": p.lipila_reference_id,
                "payment_method": p.payment_method or "manual",
                "status": p.status or "completed",
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            }
            for p in payments
        ],
        "announcements": [
            {
                "id": a.id,
                "title": a.title,
                "message": a.message,
                "class_id": a.class_id,
                "class_name": class_map.get(a.class_id, "All Classes") if a.class_id else "All Classes",
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in announcements
        ],
        "timetable": [
            {
                "id": tt.id,
                "class_id": tt.class_id,
                "class_name": class_map.get(tt.class_id, "—"),
                "subject_id": tt.subject_id,
                "subject_name": subj_map.get(tt.subject_id, "—"),
                "teacher_id": tt.teacher_id,
                "teacher_name": teacher_map.get(tt.teacher_id, "—"),
                "term_id": tt.term_id,
                "term_name": term_map.get(tt.term_id, "—"),
                "day": tt.day,
                "start_time": tt.start_time,
                "end_time": tt.end_time,
                "room": tt.room or "",
                "is_active": tt.is_active if tt.is_active is not None else True,
            }
            for tt in timetables
        ],
        "parents": [
            {
                "id": p.id,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "phone": p.phone or "",
                "email": p.email or "",
                "address": p.address or "",
                "user_id": p.user_id,
                "username": p.user.username if p.user else "",
                "linked_students": [
                    {
                        "id": ps.student.id,
                        "name": f"{ps.student.first_name} {ps.student.last_name}",
                        "admission_no": ps.student.admission_no,
                        "class_name": class_map.get(ps.student.class_id, "—"),
                    }
                    for ps in ParentStudent.query.filter_by(school_id=school_id, parent_id=p.id).all()
                    if ps.student
                ],
            }
            for p in Parent.query.filter_by(school_id=school_id).all()
        ],
    })


@api.route("/admin/students", methods=["POST"])
@login_required
def api_admin_create_student():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    if not check_plan_limit("students"):
        return jsonify({"error": "Your school has reached its plan's student limit. Please upgrade your plan."}), 403

    data = request.get_json(silent=True) or request.form
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    admission_no = (data.get("admission_no") or "").strip()
    gender = (data.get("gender") or "").strip()
    class_id = data.get("class_id")
    raw_phone = data.get("phone")
    parent_username = (data.get("parent_username") or "").strip()
    raw_parent_phone = data.get("parent_phone")

    if not all([first_name, last_name, admission_no, gender, class_id]):
        return jsonify({"error": "First name, last name, admission number, gender, and class are required."}), 400

    phone = None
    if raw_phone:
        try:
            phone = validate_and_normalize_phone(raw_phone, required=False)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    parent_phone = None
    if raw_parent_phone:
        try:
            parent_phone = validate_and_normalize_phone(raw_parent_phone, required=False)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    try:
        class_id = int(class_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid class selected."}), 400

    if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
        return jsonify({"error": "Selected class does not belong to your school."}), 403

    if Student.query.filter_by(school_id=school_id, admission_no=admission_no).first():
        return jsonify({"error": "Admission number already exists in your school."}), 400

    student = Student(
        school_id=school_id,
        first_name=first_name,
        last_name=last_name,
        admission_no=admission_no,
        gender=gender,
        phone=phone or None,
        status="active",
        class_id=class_id,
    )
    db.session.add(student)
    db.session.flush()

    user = User(
        school_id=school_id,
        username=admission_no,
        role="student",
        student_id=student.id,
        password_hash=generate_password_hash("student123"),
        is_verified=True,
    )
    db.session.add(user)
    db.session.flush()
    student.user_id = user.id

    if parent_username:
        parent_user = User.query.filter_by(
            school_id=school_id, username=parent_username, role="parent"
        ).first()
        if not parent_user:
            parent_user = User(
                school_id=school_id,
                username=parent_username,
                role="parent",
                password_hash=generate_password_hash("parent123"),
                is_verified=True,
            )
            db.session.add(parent_user)
            db.session.flush()

        parent_rec = Parent.query.filter_by(
            school_id=school_id, user_id=parent_user.id
        ).first()
        if not parent_rec:
            parent_rec = Parent(
                school_id=school_id,
                user_id=parent_user.id,
                first_name=f"Parent of {first_name}",
                last_name=last_name,
                phone=parent_phone or None,
            )
            db.session.add(parent_rec)
            db.session.flush()
        elif parent_phone:
            parent_rec.phone = parent_phone

        student.parent_id = parent_rec.id
        db.session.add(
            ParentStudent(school_id=school_id, parent_id=parent_rec.id, student_id=student.id)
        )

    record_activity(
        "student",
        "student_created",
        f"Student account created ({admission_no}) in class ID {class_id}.",
        school_id=school_id,
        target_type="student",
        target_id=admission_no,
        commit=False,
    )
    db.session.commit()
    return jsonify({
        "message": f"Student {first_name} {last_name} ({admission_no}) registered! Default password: student123",
        "student_id": student.id,
    }), 201


@api.route("/admin/students/<int:student_id>", methods=["PUT"])
@login_required
def api_admin_update_student(student_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    student = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    first_name = (data.get("first_name") or student.first_name).strip()
    last_name = (data.get("last_name") or student.last_name).strip()
    admission_no = (data.get("admission_no") or student.admission_no).strip()
    gender = (data.get("gender") or student.gender).strip()
    status = (data.get("status") or student.status or "active").strip().lower()
    class_id_val = data.get("class_id")

    raw_phone = data.get("phone")
    phone = student.phone
    if raw_phone is not None:
        try:
            phone = validate_and_normalize_phone(raw_phone, required=False)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    raw_parent_phone = data.get("parent_phone")
    parent_phone = None
    if raw_parent_phone is not None:
        try:
            parent_phone = validate_and_normalize_phone(raw_parent_phone, required=False)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    if not all([first_name, last_name, admission_no]):
        return jsonify({"error": "First name, last name, and admission number are required."}), 400

    # Check admission number uniqueness if changed
    if admission_no != student.admission_no:
        existing = Student.query.filter(
            Student.school_id == school_id,
            Student.admission_no == admission_no,
            Student.id != student.id,
        ).first()
        if existing:
            return jsonify({"error": f"Admission number '{admission_no}' is already used by another student."}), 400

    # Handle class change / transfer
    old_class_name = student.school_class.name if student.school_class else "Unassigned"
    if class_id_val is not None:
        try:
            new_class_id = int(class_id_val)
            target_class = SchoolClass.query.filter_by(id=new_class_id, school_id=school_id).first()
            if not target_class:
                return jsonify({"error": "Selected class does not exist in your school."}), 400
            if student.class_id != new_class_id:
                record_activity(
                    "student",
                    "student_transferred",
                    f"Student {student.admission_no} ({first_name} {last_name}) transferred from {old_class_name} to {target_class.name}.",
                    school_id=school_id,
                    target_type="student",
                    target_id=student.admission_no,
                    commit=False,
                )
                student.class_id = new_class_id
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid class selected."}), 400

    student.first_name = first_name
    student.last_name = last_name
    student.admission_no = admission_no
    student.gender = gender
    student.phone = phone or None
    student.status = status

    # Update parent phone if provided
    if parent_phone is not None and student.parent_id:
        parent = Parent.query.filter_by(id=student.parent_id, school_id=school_id).first()
        if parent:
            parent.phone = parent_phone or None

    # Update linked User username if admission_no changed
    if student.user_id:
        user = db.session.get(User, student.user_id)
        if user and user.username != admission_no:
            user.username = admission_no

    record_activity(
        "student",
        "student_updated",
        f"Student record updated for {admission_no} ({first_name} {last_name}).",
        school_id=school_id,
        target_type="student",
        target_id=admission_no,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Student '{first_name} {last_name}' updated successfully."})


@api.route("/admin/students/<int:student_id>/status", methods=["POST"])
@login_required
def api_admin_set_student_status(student_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    student = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    new_status = (data.get("status") or "").strip().lower()
    allowed = ["active", "transferred", "graduated", "archived"]
    if new_status not in allowed:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(allowed)}."}), 400

    old_status = student.status or "active"
    student.status = new_status
    record_activity(
        "student",
        "student_status_changed",
        f"Student {student.admission_no} status changed from {old_status} to {new_status}.",
        school_id=school_id,
        target_type="student",
        target_id=student.admission_no,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Student {student.admission_no} status updated to '{new_status}'."})


@api.route("/admin/students/<int:student_id>", methods=["DELETE"])
@login_required
def api_admin_delete_student(student_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    student = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()

    # Block deletion if dependent records exist
    pay_count = Payment.query.filter_by(school_id=school_id, student_id=student.id).count()
    res_count = Result.query.filter_by(school_id=school_id, student_id=student.id).count()
    att_count = Attendance.query.filter_by(school_id=school_id, student_id=student.id).count()

    if pay_count > 0 or res_count > 0 or att_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete student with historical records ({pay_count} payment(s), "
                f"{res_count} exam mark(s), {att_count} attendance day(s)). "
                f"Please update their status to 'Archived' or 'Transferred' instead to preserve audit logs."
            )
        }), 400

    # Delete ParentStudent links
    ParentStudent.query.filter_by(school_id=school_id, student_id=student.id).delete()

    # Delete User account
    if student.user_id:
        User.query.filter_by(id=student.user_id, school_id=school_id).delete()

    adm = student.admission_no
    name = f"{student.first_name} {student.last_name}"
    db.session.delete(student)
    record_activity(
        "student",
        "student_deleted",
        f"Student record deleted ({adm}, {name}).",
        school_id=school_id,
        target_type="student",
        target_id=adm,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Student record for {name} ({adm}) deleted successfully."})


@api.route("/admin/teachers", methods=["POST"])
@login_required
def api_admin_create_teacher():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    if not check_plan_limit("teachers"):
        return jsonify({"error": "Your school has reached its plan's teacher limit. Please upgrade your plan."}), 403

    data = request.get_json(silent=True) or request.form
    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    raw_phone = (data.get("phone") or "").strip()
    specialization = (data.get("subject_specialization") or "").strip()
    email = (data.get("email") or "").strip()

    if not all([first_name, last_name, raw_phone]):
        return jsonify({"error": "First name, last name, and phone number are required."}), 400

    try:
        phone = validate_and_normalize_phone(raw_phone, required=True)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    staff_no = "ST" + str(random.randint(1000, 9999))
    while Teacher.query.filter_by(school_id=school_id, staff_no=staff_no).first():
        staff_no = "ST" + str(random.randint(1000, 9999))

    user = User(
        school_id=school_id,
        username=staff_no,
        email=email or None,
        role="teacher",
        password_hash=generate_password_hash("teacher123"),
        is_verified=True,
    )
    db.session.add(user)
    db.session.flush()

    teacher = Teacher(
        school_id=school_id,
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email or None,
        subject_specialization=specialization or None,
        staff_no=staff_no,
        is_active=True,
    )
    db.session.add(teacher)
    record_activity(
        "staff",
        "teacher_created",
        f"Teacher staff account created ({staff_no}, {specialization or 'General'}).",
        school_id=school_id,
        target_type="teacher",
        target_id=staff_no,
        commit=False,
    )
    db.session.commit()

    return jsonify({
        "message": f"Teacher registered! Staff Username: {staff_no} (Default password: teacher123)",
        "staff_no": staff_no,
        "id": teacher.id,
    }), 201


@api.route("/admin/teachers/<int:teacher_id>", methods=["PUT"])
@login_required
def api_admin_update_teacher(teacher_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    teacher = Teacher.query.filter_by(id=teacher_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    first_name = (data.get("first_name") or teacher.first_name).strip()
    last_name = (data.get("last_name") or teacher.last_name).strip()
    specialization = (data.get("subject_specialization") or teacher.subject_specialization or "").strip()
    email = (data.get("email") or teacher.email or "").strip()

    raw_phone = data.get("phone")
    phone = teacher.phone
    if raw_phone:
        try:
            phone = validate_and_normalize_phone(raw_phone, required=True)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    if not all([first_name, last_name, phone]):
        return jsonify({"error": "First name, last name, and phone number are required."}), 400

    teacher.first_name = first_name
    teacher.last_name = last_name
    teacher.phone = phone
    teacher.email = email or None
    teacher.subject_specialization = specialization or None

    if teacher.user_id:
        user = db.session.get(User, teacher.user_id)
        if user:
            user.email = email or None

    record_activity(
        "staff",
        "teacher_updated",
        f"Teacher record updated for {teacher.staff_no} ({first_name} {last_name}).",
        school_id=school_id,
        target_type="teacher",
        target_id=teacher.staff_no,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Teacher {first_name} {last_name} ({teacher.staff_no}) updated successfully."})


@api.route("/admin/teachers/<int:teacher_id>/toggle-status", methods=["POST"])
@login_required
def api_admin_toggle_teacher_status(teacher_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    teacher = Teacher.query.filter_by(id=teacher_id, school_id=school_id).first_or_404()

    new_active = not (teacher.is_active if teacher.is_active is not None else True)
    teacher.is_active = new_active

    notice = ""
    if not new_active:
        active_slots = Timetable.query.filter_by(school_id=school_id, teacher_id=teacher.id).count()
        notice = f" Deactivated. Note: teacher has {active_slots} existing timetable assignment(s) that may require reassignment."
    else:
        notice = " Reactivated successfully."

    record_activity(
        "staff",
        "teacher_status_toggled",
        f"Teacher {teacher.staff_no} active state changed to {new_active}.",
        school_id=school_id,
        target_type="teacher",
        target_id=teacher.staff_no,
        commit=False,
    )
    db.session.commit()
    return jsonify({
        "message": f"Teacher {teacher.first_name} {teacher.last_name}{notice}",
        "is_active": teacher.is_active,
    })


@api.route("/admin/teachers/<int:teacher_id>", methods=["DELETE"])
@login_required
def api_admin_delete_teacher(teacher_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    teacher = Teacher.query.filter_by(id=teacher_id, school_id=school_id).first_or_404()

    # Check dependencies
    tt_count = Timetable.query.filter_by(school_id=school_id, teacher_id=teacher.id).count()
    class_count = SchoolClass.query.filter_by(school_id=school_id, class_teacher_id=teacher.id).count()

    if tt_count > 0 or class_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete teacher with existing records ({tt_count} timetable slot(s), "
                f"{class_count} class teacher role(s)). Please deactivate the teacher instead to retain academic history."
            )
        }), 400

    staff_no = teacher.staff_no
    name = f"{teacher.first_name} {teacher.last_name}"

    if teacher.user_id:
        User.query.filter_by(id=teacher.user_id, school_id=school_id).delete()

    db.session.delete(teacher)
    record_activity(
        "staff",
        "teacher_deleted",
        f"Teacher record deleted ({staff_no}, {name}).",
        school_id=school_id,
        target_type="teacher",
        target_id=staff_no,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Teacher {name} ({staff_no}) deleted successfully."})


@api.route("/admin/classes", methods=["POST"])
@login_required
def api_admin_create_class():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    capacity = data.get("capacity")
    grade_level = (data.get("grade_level") or "").strip()
    academic_year = (data.get("academic_year") or "").strip()
    class_teacher_id = data.get("class_teacher_id")

    if not name or not capacity:
        return jsonify({"error": "Class name and capacity are required."}), 400
    try:
        capacity = int(capacity)
        if capacity <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Capacity must be a positive integer."}), 400

    if SchoolClass.query.filter_by(school_id=school_id, name=name).first():
        return jsonify({"error": f"A class with name '{name}' already exists in your school."}), 400

    teacher_fk = None
    if class_teacher_id:
        try:
            tid = int(class_teacher_id)
            if Teacher.query.filter_by(id=tid, school_id=school_id).first():
                teacher_fk = tid
        except (ValueError, TypeError):
            pass

    c = SchoolClass(
        school_id=school_id,
        name=name,
        capacity=capacity,
        grade_level=grade_level or None,
        academic_year=academic_year or None,
        class_teacher_id=teacher_fk,
        is_active=True,
    )
    db.session.add(c)
    record_activity(
        "academic",
        "class_created",
        f"Class '{name}' created (capacity: {capacity}).",
        school_id=school_id,
        target_type="class",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Class '{name}' created.", "id": c.id}), 201


@api.route("/admin/classes/<int:class_id>", methods=["PUT"])
@login_required
def api_admin_update_class(class_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    c = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or c.name).strip()
    capacity_val = data.get("capacity")
    grade_level = (data.get("grade_level") or c.grade_level or "").strip()
    academic_year = (data.get("academic_year") or c.academic_year or "").strip()
    class_teacher_id = data.get("class_teacher_id")

    if not name:
        return jsonify({"error": "Class name is required."}), 400

    # Check duplicate name
    existing = SchoolClass.query.filter(
        SchoolClass.school_id == school_id,
        SchoolClass.name == name,
        SchoolClass.id != c.id,
    ).first()
    if existing:
        return jsonify({"error": f"Another class named '{name}' already exists."}), 400

    if capacity_val is not None:
        try:
            cap = int(capacity_val)
            if cap <= 0:
                raise ValueError
            c.capacity = cap
        except (ValueError, TypeError):
            return jsonify({"error": "Capacity must be a positive number."}), 400

    if class_teacher_id is not None:
        if class_teacher_id == "" or class_teacher_id == 0 or class_teacher_id == "0":
            c.class_teacher_id = None
        else:
            try:
                tid = int(class_teacher_id)
                if Teacher.query.filter_by(id=tid, school_id=school_id).first():
                    c.class_teacher_id = tid
            except (ValueError, TypeError):
                pass

    c.name = name
    c.grade_level = grade_level or None
    c.academic_year = academic_year or None

    record_activity(
        "academic",
        "class_updated",
        f"Class '{name}' updated.",
        school_id=school_id,
        target_type="class",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Class '{name}' updated successfully."})


@api.route("/admin/classes/<int:class_id>", methods=["DELETE"])
@login_required
def api_admin_delete_class(class_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    c = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()

    stu_count = Student.query.filter_by(school_id=school_id, class_id=c.id).count()
    tt_count = Timetable.query.filter_by(school_id=school_id, class_id=c.id).count()

    if stu_count > 0 or tt_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete class '{c.name}' because it contains {stu_count} student(s) and {tt_count} timetable slot(s). "
                f"Please transfer the students to another class or clear their schedules first."
            )
        }), 400

    name = c.name
    db.session.delete(c)
    record_activity(
        "academic",
        "class_deleted",
        f"Class '{name}' deleted.",
        school_id=school_id,
        target_type="class",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Class '{name}' deleted successfully."})


@api.route("/admin/subjects", methods=["POST"])
@login_required
def api_admin_create_subject():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip().upper()
    description = (data.get("description") or "").strip()

    if not name or not code:
        return jsonify({"error": "Subject name and code are required."}), 400
    if Subject.query.filter_by(school_id=school_id, code=code).first():
        return jsonify({"error": "Subject code already exists in your school."}), 400

    s = Subject(school_id=school_id, name=name, code=code, description=description or None, is_active=True)
    db.session.add(s)
    db.session.commit()
    return jsonify({"message": f"Subject '{name} ({code})' added.", "id": s.id}), 201


@api.route("/admin/subjects/<int:subject_id>", methods=["PUT"])
@login_required
def api_admin_update_subject(subject_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    s = Subject.query.filter_by(id=subject_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or s.name).strip()
    code = (data.get("code") or s.code).strip().upper()
    description = (data.get("description") or s.description or "").strip()

    if not name or not code:
        return jsonify({"error": "Subject name and code are required."}), 400

    existing = Subject.query.filter(
        Subject.school_id == school_id,
        Subject.code == code,
        Subject.id != s.id,
    ).first()
    if existing:
        return jsonify({"error": f"Subject code '{code}' is already used by another subject."}), 400

    s.name = name
    s.code = code
    s.description = description or None
    db.session.commit()
    return jsonify({"message": f"Subject '{name} ({code})' updated successfully."})


@api.route("/admin/subjects/<int:subject_id>/toggle-status", methods=["POST"])
@login_required
def api_admin_toggle_subject_status(subject_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    s = Subject.query.filter_by(id=subject_id, school_id=school_id).first_or_404()

    s.is_active = not (s.is_active if s.is_active is not None else True)
    db.session.commit()
    status_str = "active" if s.is_active else "inactive/archived"
    return jsonify({"message": f"Subject '{s.name}' marked as {status_str}.", "is_active": s.is_active})


@api.route("/admin/subjects/<int:subject_id>", methods=["DELETE"])
@login_required
def api_admin_delete_subject(subject_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    s = Subject.query.filter_by(id=subject_id, school_id=school_id).first_or_404()

    res_count = Result.query.filter_by(school_id=school_id, subject_id=s.id).count()
    tt_count = Timetable.query.filter_by(school_id=school_id, subject_id=s.id).count()

    if res_count > 0 or tt_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete subject '{s.name}' because it has {res_count} student grade(s) and {tt_count} timetable slot(s). "
                f"Please toggle the subject to inactive/archived instead to preserve historical records."
            )
        }), 400

    name = s.name
    code = s.code
    db.session.delete(s)
    db.session.commit()
    return jsonify({"message": f"Subject '{name} ({code})' deleted successfully."})


@api.route("/admin/terms", methods=["POST"])
@login_required
def api_admin_create_term():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    start_str = data.get("start_date")
    end_str = data.get("end_date")

    if not all([name, start_str, end_str]):
        return jsonify({"error": "Term name, start date, and end date are required."}), 400
    try:
        start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Dates must be in YYYY-MM-DD format."}), 400

    if end_date <= start_date:
        return jsonify({"error": "Term end date must be after start date."}), 400

    t = Term(school_id=school_id, name=name, start_date=start_date, end_date=end_date, is_active=True)
    db.session.add(t)
    record_activity(
        "academic",
        "term_created",
        f"Academic term '{name}' created ({start_date.isoformat()} to {end_date.isoformat()}).",
        school_id=school_id,
        target_type="term",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Term '{name}' created.", "id": t.id}), 201


@api.route("/admin/terms/<int:term_id>", methods=["PUT"])
@login_required
def api_admin_update_term(term_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    t = Term.query.filter_by(id=term_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or t.name).strip()
    start_str = data.get("start_date")
    end_str = data.get("end_date")
    is_active_val = data.get("is_active")

    if not name:
        return jsonify({"error": "Term name is required."}), 400

    start_date = t.start_date
    end_date = t.end_date

    if start_str:
        try:
            start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "Start date must be in YYYY-MM-DD format."}), 400

    if end_str:
        try:
            end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "End date must be in YYYY-MM-DD format."}), 400

    if end_date <= start_date:
        return jsonify({"error": "Term end date must be after start date."}), 400

    t.name = name
    t.start_date = start_date
    t.end_date = end_date
    if is_active_val is not None:
        t.is_active = bool(is_active_val)

    record_activity(
        "academic",
        "term_updated",
        f"Academic term '{name}' updated.",
        school_id=school_id,
        target_type="term",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Term '{name}' updated successfully."})


@api.route("/admin/terms/<int:term_id>", methods=["DELETE"])
@login_required
def api_admin_delete_term(term_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    t = Term.query.filter_by(id=term_id, school_id=school_id).first_or_404()

    exam_count = Exam.query.filter_by(school_id=school_id, term_id=t.id).count()
    fee_count = FeeStructure.query.filter_by(school_id=school_id, term_id=t.id).count()
    pay_count = Payment.query.filter_by(school_id=school_id, term_id=t.id).count()

    if exam_count > 0 or fee_count > 0 or pay_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete term '{t.name}' because it has {exam_count} exam(s), {fee_count} fee structure(s), "
                f"and {pay_count} payment record(s). Please edit the term or set it to inactive instead."
            )
        }), 400

    name = t.name
    db.session.delete(t)
    db.session.commit()
    return jsonify({"message": f"Term '{name}' deleted successfully."})


@api.route("/admin/exams", methods=["POST"])
@login_required
def api_admin_create_exam():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    term_id = data.get("term_id")
    class_id = data.get("class_id")
    subject_id = data.get("subject_id")
    start_date_str = data.get("start_date") or data.get("date")
    end_date_str = data.get("end_date") or start_date_str
    start_time = (data.get("start_time") or "").strip()
    end_time = (data.get("end_time") or "").strip()
    venue = (data.get("venue") or "").strip()
    exam_type = (data.get("exam_type") or "Main").strip()

    if not name or not term_id:
        return jsonify({"error": "Exam name and term are required."}), 400
    try:
        term_id = int(term_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid term selected."}), 400

    target_term = Term.query.filter_by(id=term_id, school_id=school_id).first()
    if not target_term:
        return jsonify({"error": "Selected term does not belong to your school."}), 403

    start_date = None
    if start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "Exam start date must be in YYYY-MM-DD format."}), 400

    end_date = None
    if end_date_str:
        try:
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "Exam end date must be in YYYY-MM-DD format."}), 400
    elif start_date:
        end_date = start_date

    if start_date and end_date and end_date < start_date:
        return jsonify({"error": "Exam end date cannot be earlier than start date."}), 400

    if target_term.start_date and start_date and start_date < target_term.start_date:
        return jsonify({"error": f"Exam start date ({start_date.isoformat()}) cannot be before term start date ({target_term.start_date.isoformat()})."}), 400
    if target_term.end_date and end_date and end_date > target_term.end_date:
        return jsonify({"error": f"Exam end date ({end_date.isoformat()}) cannot be after term end date ({target_term.end_date.isoformat()})."}), 400

    if start_time and end_time:
        if end_time <= start_time:
            return jsonify({"error": "Exam end time must be after start time."}), 400

    cid = None
    if class_id:
        try:
            cid = int(class_id)
        except (ValueError, TypeError):
            pass

    sid = None
    if subject_id:
        try:
            sid = int(subject_id)
        except (ValueError, TypeError):
            pass

    e = Exam(
        school_id=school_id,
        name=name,
        term_id=term_id,
        class_id=cid,
        subject_id=sid,
        date=start_date,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time or None,
        end_time=end_time or None,
        venue=venue or None,
        exam_type=exam_type or "Main",
        status="scheduled",
    )
    db.session.add(e)
    record_activity(
        "exam",
        "exam_created",
        f"Examination '{name}' scheduled for term ID {term_id}.",
        school_id=school_id,
        target_type="exam",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Exam '{name}' created.", "id": e.id}), 201


@api.route("/admin/exams/<int:exam_id>", methods=["PUT"])
@login_required
def api_admin_update_exam(exam_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    e = Exam.query.filter_by(id=exam_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or e.name).strip()
    term_id = data.get("term_id")
    class_id = data.get("class_id")
    subject_id = data.get("subject_id")
    start_date_str = data.get("start_date") or data.get("date")
    end_date_str = data.get("end_date")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    venue = data.get("venue")
    exam_type = data.get("exam_type")
    status = data.get("status")

    if not name:
        return jsonify({"error": "Exam name is required."}), 400

    if term_id:
        try:
            tid = int(term_id)
            if Term.query.filter_by(id=tid, school_id=school_id).first():
                e.term_id = tid
        except (ValueError, TypeError):
            pass

    if start_date_str:
        try:
            parsed_start = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            e.start_date = parsed_start
            e.date = parsed_start
        except (ValueError, TypeError):
            return jsonify({"error": "Start date must be in YYYY-MM-DD format."}), 400
    elif start_date_str == "":
        e.start_date = None
        e.date = None

    if end_date_str:
        try:
            e.end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return jsonify({"error": "End date must be in YYYY-MM-DD format."}), 400
    elif end_date_str == "":
        e.end_date = e.start_date
    elif e.start_date and not e.end_date:
        e.end_date = e.start_date

    if e.start_date and e.end_date and e.end_date < e.start_date:
        return jsonify({"error": "Exam end date cannot be earlier than start date."}), 400

    target_term = Term.query.filter_by(id=e.term_id, school_id=school_id).first()
    if target_term:
        if target_term.start_date and e.start_date and e.start_date < target_term.start_date:
            return jsonify({"error": f"Exam start date cannot be before term start date ({target_term.start_date.isoformat()})."}), 400
        if target_term.end_date and e.end_date and e.end_date > target_term.end_date:
            return jsonify({"error": f"Exam end date cannot be after term end date ({target_term.end_date.isoformat()})."}), 400

    new_start = (start_time if start_time is not None else (e.start_time or "")).strip()
    new_end = (end_time if end_time is not None else (e.end_time or "")).strip()
    if new_start and new_end and new_end <= new_start:
        return jsonify({"error": "Exam end time must be after start time."}), 400

    e.name = name
    e.start_time = new_start or None
    e.end_time = new_end or None
    if venue is not None:
        e.venue = venue.strip() or None
    if exam_type is not None:
        e.exam_type = exam_type.strip() or "Main"
    if status is not None:
        e.status = status.strip().lower() or "scheduled"

    if class_id is not None:
        if class_id == "" or class_id == 0 or class_id == "0":
            e.class_id = None
        else:
            try:
                cid = int(class_id)
                if SchoolClass.query.filter_by(id=cid, school_id=school_id).first():
                    e.class_id = cid
            except (ValueError, TypeError):
                pass

    if subject_id is not None:
        if subject_id == "" or subject_id == 0 or subject_id == "0":
            e.subject_id = None
        else:
            try:
                sid = int(subject_id)
                if Subject.query.filter_by(id=sid, school_id=school_id).first():
                    e.subject_id = sid
            except (ValueError, TypeError):
                pass

    record_activity(
        "exam",
        "exam_updated",
        f"Examination '{name}' rescheduled/updated.",
        school_id=school_id,
        target_type="exam",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Exam '{name}' updated successfully."})


@api.route("/admin/exams/<int:exam_id>", methods=["DELETE"])
@login_required
def api_admin_delete_exam(exam_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    e = Exam.query.filter_by(id=exam_id, school_id=school_id).first_or_404()

    res_count = Result.query.filter_by(school_id=school_id, exam_id=e.id).count()
    if res_count > 0:
        return jsonify({
            "error": (
                f"Cannot delete exam '{e.name}' because {res_count} student grade(s) have already been entered. "
                f"Please update the exam status to 'cancelled' instead to keep student records intact."
            )
        }), 400

    name = e.name
    db.session.delete(e)
    record_activity(
        "exam",
        "exam_deleted",
        f"Examination '{name}' deleted.",
        school_id=school_id,
        target_type="exam",
        target_id=name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Exam '{name}' deleted successfully."})


@api.route("/admin/fees", methods=["POST"])
@login_required
def api_admin_set_fees():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    class_id = data.get("class_id")
    term_id = data.get("term_id")
    amount = data.get("amount")

    try:
        class_id = int(class_id)
        term_id = int(term_id)
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Valid class, term, and positive ZMW amount are required."}), 400

    if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
        return jsonify({"error": "Invalid class for your school."}), 403
    if not Term.query.filter_by(id=term_id, school_id=school_id).first():
        return jsonify({"error": "Invalid term for your school."}), 403

    existing = FeeStructure.query.filter_by(
        school_id=school_id, class_id=class_id, term_id=term_id
    ).first()
    if existing:
        existing.amount = amount
        db.session.commit()
        return jsonify({"message": "Fee structure updated successfully.", "id": existing.id})

    f = FeeStructure(school_id=school_id, class_id=class_id, term_id=term_id, amount=amount)
    db.session.add(f)
    db.session.commit()
    return jsonify({"message": "Fee structure saved successfully.", "id": f.id}), 201


@api.route("/admin/manual-payment", methods=["POST"])
@login_required
def api_admin_manual_payment():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form

    student_id = data.get("student_id")
    term_id = data.get("term_id")
    amount = data.get("amount")
    bank_reference = (data.get("bank_reference") or "").strip()
    payment_date_str = data.get("payment_date") or datetime.date.today().isoformat()

    if not all([student_id, term_id, amount, bank_reference]):
        return jsonify({"error": "Student, term, amount, and bank reference are required."}), 400

    try:
        student_id = int(student_id)
        term_id = int(term_id)
        amount = float(amount)
        if amount <= 0:
            raise ValueError
        payment_date = datetime.datetime.strptime(payment_date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid payment input values."}), 400

    student = Student.query.filter_by(id=student_id, school_id=school_id).first()
    term = Term.query.filter_by(id=term_id, school_id=school_id).first()
    if not student or not term:
        return jsonify({"error": "Student or term does not belong to your school."}), 404

    if Payment.query.filter_by(school_id=school_id, bank_reference=bank_reference).first():
        return jsonify({"error": "This bank reference has already been recorded."}), 400

    reference = generate_unique_reference(school_id)
    payment = Payment(
        school_id=school_id,
        student_id=student.id,
        term_id=term.id,
        amount_paid=amount,
        currency="ZMW",
        reference=reference,
        bank_reference=bank_reference,
        payment_method="manual",
        status="completed",
        payment_date=payment_date,
    )
    db.session.add(payment)
    record_activity(
        "payment",
        "fee_payment_confirmed",
        f"Manual fee payment recorded ({student.admission_no}) — K{amount:.2f} (Receipt: {reference}).",
        school_id=school_id,
        status="success",
        target_type="payment",
        target_id=reference,
        commit=False,
    )
    db.session.commit()
    return jsonify({
        "message": f"Payment recorded! Receipt: {reference}",
        "payment_id": payment.id,
        "reference": reference,
    }), 201


@api.route("/admin/timetable", methods=["POST"])
@login_required
def api_admin_create_timetable():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form

    try:
        class_id = int(data.get("class_id"))
        subject_id = int(data.get("subject_id"))
        teacher_id = int(data.get("teacher_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Class, subject, and teacher are required."}), 400

    day = (data.get("day") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    end_time = (data.get("end_time") or "").strip()
    room = (data.get("room") or "").strip()
    term_id_val = data.get("term_id")

    if not all([day, start_time, end_time]):
        return jsonify({"error": "Day, start time, and end time are required."}), 400

    if end_time <= start_time:
        return jsonify({"error": "End time must be after start time."}), 400

    target_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first()
    target_subject = Subject.query.filter_by(id=subject_id, school_id=school_id).first()
    target_teacher = Teacher.query.filter_by(id=teacher_id, school_id=school_id).first()

    if not target_class:
        return jsonify({"error": "Selected class does not belong to your school."}), 403
    if not target_subject:
        return jsonify({"error": "Selected subject does not belong to your school."}), 403
    if not target_teacher:
        return jsonify({"error": "Selected teacher does not belong to your school."}), 403

    # Check if teacher is active
    if not (target_teacher.is_active if target_teacher.is_active is not None else True):
        return jsonify({
            "error": f"Teacher {target_teacher.first_name} {target_teacher.last_name} is marked as inactive and cannot receive new timetable assignments."
        }), 400

    # 1. Teacher Clash Check
    teacher_clash = Timetable.query.filter(
        Timetable.school_id == school_id,
        Timetable.teacher_id == teacher_id,
        Timetable.day == day,
        Timetable.start_time < end_time,
        Timetable.end_time > start_time,
    ).first()
    if teacher_clash:
        clash_class = db.session.get(SchoolClass, teacher_clash.class_id)
        c_name = clash_class.name if clash_class else "another class"
        return jsonify({
            "error": (
                f"Teacher schedule clash: {target_teacher.first_name} {target_teacher.last_name} is already teaching "
                f"{c_name} on {day} from {teacher_clash.start_time} to {teacher_clash.end_time}."
            )
        }), 400

    # 2. Class Clash Check
    class_clash = Timetable.query.filter(
        Timetable.school_id == school_id,
        Timetable.class_id == class_id,
        Timetable.day == day,
        Timetable.start_time < end_time,
        Timetable.end_time > start_time,
    ).first()
    if class_clash:
        clash_subj = db.session.get(Subject, class_clash.subject_id)
        s_name = clash_subj.name if clash_subj else "another subject"
        return jsonify({
            "error": (
                f"Class schedule clash: {target_class.name} is already scheduled for {s_name} "
                f"on {day} from {class_clash.start_time} to {class_clash.end_time}."
            )
        }), 400

    # 3. Room Clash Check
    if room:
        room_clash = Timetable.query.filter(
            Timetable.school_id == school_id,
            Timetable.room == room,
            Timetable.day == day,
            Timetable.start_time < end_time,
            Timetable.end_time > start_time,
        ).first()
        if room_clash:
            clash_class = db.session.get(SchoolClass, room_clash.class_id)
            c_name = clash_class.name if clash_class else "another class"
            return jsonify({
                "error": (
                    f"Room clash: Room '{room}' is already booked for {c_name} "
                    f"on {day} from {room_clash.start_time} to {room_clash.end_time}."
                )
            }), 400

    term_fk = None
    if term_id_val:
        try:
            term_fk = int(term_id_val)
        except (ValueError, TypeError):
            pass

    tt = Timetable(
        school_id=school_id,
        class_id=class_id,
        subject_id=subject_id,
        teacher_id=teacher_id,
        term_id=term_fk,
        day=day,
        start_time=start_time,
        end_time=end_time,
        room=room or None,
        is_active=True,
    )
    db.session.add(tt)
    db.session.commit()
    return jsonify({"message": f"Timetable slot added: {target_class.name} - {target_subject.name} on {day}.", "id": tt.id}), 201


@api.route("/admin/timetable/<int:timetable_id>", methods=["PUT"])
@login_required
def api_admin_update_timetable(timetable_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    tt = Timetable.query.filter_by(id=timetable_id, school_id=school_id).first_or_404()

    data = request.get_json(silent=True) or request.form
    try:
        class_id = int(data.get("class_id") or tt.class_id)
        subject_id = int(data.get("subject_id") or tt.subject_id)
        teacher_id = int(data.get("teacher_id") or tt.teacher_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Class, subject, and teacher are required."}), 400

    day = (data.get("day") or tt.day).strip()
    start_time = (data.get("start_time") or tt.start_time).strip()
    end_time = (data.get("end_time") or tt.end_time).strip()
    room = data.get("room")
    room_val = (room if room is not None else (tt.room or "")).strip()

    if not all([day, start_time, end_time]):
        return jsonify({"error": "Day, start time, and end time are required."}), 400

    if end_time <= start_time:
        return jsonify({"error": "End time must be after start time."}), 400

    target_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first()
    target_subject = Subject.query.filter_by(id=subject_id, school_id=school_id).first()
    target_teacher = Teacher.query.filter_by(id=teacher_id, school_id=school_id).first()

    if not target_class or not target_subject or not target_teacher:
        return jsonify({"error": "Invalid class, subject, or teacher."}), 400

    # 1. Teacher Clash Check (excluding this slot)
    teacher_clash = Timetable.query.filter(
        Timetable.school_id == school_id,
        Timetable.teacher_id == teacher_id,
        Timetable.day == day,
        Timetable.id != tt.id,
        Timetable.start_time < end_time,
        Timetable.end_time > start_time,
    ).first()
    if teacher_clash:
        clash_class = db.session.get(SchoolClass, teacher_clash.class_id)
        c_name = clash_class.name if clash_class else "another class"
        return jsonify({
            "error": (
                f"Teacher schedule clash: {target_teacher.first_name} {target_teacher.last_name} is already teaching "
                f"{c_name} on {day} from {teacher_clash.start_time} to {teacher_clash.end_time}."
            )
        }), 400

    # 2. Class Clash Check (excluding this slot)
    class_clash = Timetable.query.filter(
        Timetable.school_id == school_id,
        Timetable.class_id == class_id,
        Timetable.day == day,
        Timetable.id != tt.id,
        Timetable.start_time < end_time,
        Timetable.end_time > start_time,
    ).first()
    if class_clash:
        clash_subj = db.session.get(Subject, class_clash.subject_id)
        s_name = clash_subj.name if clash_subj else "another subject"
        return jsonify({
            "error": (
                f"Class schedule clash: {target_class.name} is already scheduled for {s_name} "
                f"on {day} from {class_clash.start_time} to {class_clash.end_time}."
            )
        }), 400

    # 3. Room Clash Check (excluding this slot)
    if room_val:
        room_clash = Timetable.query.filter(
            Timetable.school_id == school_id,
            Timetable.room == room_val,
            Timetable.day == day,
            Timetable.id != tt.id,
            Timetable.start_time < end_time,
            Timetable.end_time > start_time,
        ).first()
        if room_clash:
            clash_class = db.session.get(SchoolClass, room_clash.class_id)
            c_name = clash_class.name if clash_class else "another class"
            return jsonify({
                "error": (
                    f"Room clash: Room '{room_val}' is already booked for {c_name} "
                    f"on {day} from {room_clash.start_time} to {room_clash.end_time}."
                )
            }), 400

    tt.class_id = class_id
    tt.subject_id = subject_id
    tt.teacher_id = teacher_id
    tt.day = day
    tt.start_time = start_time
    tt.end_time = end_time
    tt.room = room_val or None

    db.session.commit()
    return jsonify({"message": f"Timetable slot updated: {target_class.name} - {target_subject.name} on {day}."})


@api.route("/admin/timetable/<int:timetable_id>", methods=["DELETE"])
@login_required
def api_admin_delete_timetable(timetable_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    tt = Timetable.query.filter_by(id=timetable_id, school_id=school_id).first_or_404()

    db.session.delete(tt)
    db.session.commit()
    return jsonify({"message": "Timetable slot deleted successfully."})
    db.session.add(tt)
    db.session.commit()
    return jsonify({"message": "Timetable slot added.", "id": tt.id}), 201


@api.route("/admin/announcements", methods=["POST"])
@login_required
def api_admin_create_announcement():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    class_id_raw = data.get("class_id")

    if not title or not content:
        return jsonify({"error": "Announcement title and content are required."}), 400

    target_class_id = None
    if class_id_raw:
        try:
            target_class_id = int(class_id_raw)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid class selection."}), 400
        if not SchoolClass.query.filter_by(id=target_class_id, school_id=school_id).first():
            return jsonify({"error": "Invalid class selection."}), 403

    ann = Announcement(
        school_id=school_id,
        title=title,
        message=content,
        class_id=target_class_id,
        user_id=current_user.id,
    )
    db.session.add(ann)

    student_q = Student.query.filter_by(school_id=school_id)
    if target_class_id:
        student_q = student_q.filter_by(class_id=target_class_id)
    for stu in student_q.all():
        u = User.query.filter_by(school_id=school_id, username=stu.admission_no).first()
        if u:
            send_notification(u.id, school_id, f"New announcement: {title}", "announcement")

    record_activity(
        "announcement",
        "announcement_published",
        f"Announcement published: '{title}'.",
        school_id=school_id,
        target_type="announcement",
        target_id=title,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": "Announcement published.", "id": ann.id}), 201


@api.route("/admin/announcements/<int:ann_id>", methods=["DELETE"])
@login_required
def api_admin_delete_announcement(ann_id):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    ann = Announcement.query.filter_by(id=ann_id, school_id=school_id).first_or_404()
    db.session.delete(ann)
    db.session.commit()
    return jsonify({"message": "Announcement deleted."})


# ──────────────────────────────────────────────────────────────────
#  ADMIN PARENT PROVISIONING & STUDENT LINKING
# ──────────────────────────────────────────────────────────────────

@api.route("/admin/parents", methods=["GET"])
@login_required
def api_admin_list_parents():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    parents = Parent.query.filter_by(school_id=school_id).order_by(Parent.id.desc()).all()
    class_map = {c.id: c.name for c in SchoolClass.query.filter_by(school_id=school_id).all()}

    payload = []
    for p in parents:
        links = ParentStudent.query.filter_by(school_id=school_id, parent_id=p.id).all()
        payload.append({
            "id": p.id,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "phone": p.phone or "",
            "email": p.email or "",
            "address": p.address or "",
            "user_id": p.user_id,
            "username": p.user.username if p.user else "",
            "linked_students": [
                {
                    "id": lk.student.id,
                    "first_name": lk.student.first_name,
                    "last_name": lk.student.last_name,
                    "admission_no": lk.student.admission_no,
                    "class_name": class_map.get(lk.student.class_id, "—"),
                }
                for lk in links if lk.student
            ]
        })
    return jsonify({"parents": payload})


@api.route("/admin/parents", methods=["POST"])
@login_required
def api_admin_create_parent():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    phone_raw = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "parent123").strip()
    student_ids = data.get("student_ids") or []

    if not first_name or not last_name:
        return jsonify({"error": "First name and last name are required."}), 400

    phone = None
    if phone_raw:
        try:
            phone = validate_and_normalize_phone(phone_raw, required=False)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    if not username:
        base_username = (phone or f"{first_name.lower()}{last_name.lower()}").replace(" ", "")
        username = base_username
        suffix = 1
        while User.query.filter_by(school_id=school_id, username=username).first():
            username = f"{base_username}{suffix}"
            suffix += 1
    else:
        if User.query.filter_by(school_id=school_id, username=username).first():
            return jsonify({"error": f"Username '{username}' is already taken in this school."}), 400

    user = User(
        school_id=school_id,
        username=username,
        role="parent",
        email=email or None,
        is_verified=True,
    )
    user.set_password(password or "parent123")
    db.session.add(user)
    db.session.flush()

    parent = Parent(
        school_id=school_id,
        user_id=user.id,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        email=email or None,
        address=(data.get("address") or "").strip() or None,
    )
    db.session.add(parent)
    db.session.flush()

    linked_count = 0
    if isinstance(student_ids, (list, tuple)):
        for sid in student_ids:
            try:
                sid_int = int(sid)
                stu = Student.query.filter_by(id=sid_int, school_id=school_id).first()
                if stu:
                    db.session.add(ParentStudent(
                        school_id=school_id,
                        parent_id=parent.id,
                        student_id=stu.id,
                    ))
                    stu.parent_id = parent.id
                    linked_count += 1
            except (ValueError, TypeError):
                continue

    record_activity(
        "parent",
        "parent_created",
        f"Parent '{first_name} {last_name}' provisioned ({username}) with {linked_count} linked child(ren).",
        school_id=school_id,
        target_type="parent",
        target_id=str(parent.id),
        commit=False,
    )
    db.session.commit()
    return jsonify({
        "message": f"Parent '{first_name} {last_name}' provisioned successfully.",
        "parent_id": parent.id,
        "username": username,
    }), 201


@api.route("/admin/parents/<int:parent_id>/link-student", methods=["POST"])
@login_required
def api_admin_link_parent_student(parent_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    parent = Parent.query.filter_by(id=parent_id, school_id=school_id).first_or_404()
    data = request.get_json(silent=True) or request.form

    student_id = data.get("student_id")
    action = data.get("action", "link")

    try:
        sid_int = int(student_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid student ID."}), 400

    student = Student.query.filter_by(id=sid_int, school_id=school_id).first_or_404()

    existing = ParentStudent.query.filter_by(
        school_id=school_id, parent_id=parent.id, student_id=student.id
    ).first()

    if action == "unlink":
        if existing:
            db.session.delete(existing)
            if student.parent_id == parent.id:
                student.parent_id = None
            db.session.commit()
            return jsonify({"message": f"Student {student.first_name} unlinked from parent."})
        return jsonify({"message": "Student was not linked."})
    else:
        if not existing:
            db.session.add(ParentStudent(
                school_id=school_id,
                parent_id=parent.id,
                student_id=student.id,
            ))
            student.parent_id = parent.id
            db.session.commit()
            return jsonify({"message": f"Student {student.first_name} successfully linked to parent."})
        return jsonify({"message": "Student already linked to this parent."})


@api.route("/admin/parents/<int:parent_id>/reset-password", methods=["POST"])
@login_required
def api_admin_reset_parent_password(parent_id: int):
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    parent = Parent.query.filter_by(id=parent_id, school_id=school_id).first_or_404()
    data = request.get_json(silent=True) or request.form

    new_password = (data.get("password") or "parent123").strip()
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    if not parent.user:
        return jsonify({"error": "Parent has no associated user account."}), 400

    parent.user.set_password(new_password)
    db.session.commit()
    return jsonify({"message": f"Password reset successfully for {parent.first_name} {parent.last_name}."})


# ══════════════════════════════════════════════════════════════════
#  TEACHER PORTAL
# ══════════════════════════════════════════════════════════════════

@api.route("/teacher/overview", methods=["GET"])
@login_required
def api_teacher_overview():
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()

    teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
    all_classes = SchoolClass.query.filter_by(school_id=school_id).all()
    all_subjects = Subject.query.filter_by(school_id=school_id).all()
    all_exams = Exam.query.filter_by(school_id=school_id).all()

    class_map = {c.id: c.name for c in all_classes}
    subj_map = {s.id: s.name for s in all_subjects}

    if current_user.role == "teacher":
        if not teacher_rec:
            assigned_cids, assigned_sids, class_subj_map = set(), set(), {}
        else:
            assigned_cids, assigned_sids, class_subj_map = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)

        visible_classes = [c for c in all_classes if c.id in assigned_cids]
        visible_subjects = [s for s in all_subjects if s.id in assigned_sids]
        materials = (
            Material.query.filter(
                Material.school_id == school_id,
                db.or_(
                    Material.teacher_id == (teacher_rec.id if teacher_rec else -1),
                    Material.class_id.in_(assigned_cids) if assigned_cids else False,
                ),
            )
            .order_by(Material.id.desc())
            .all()
        )
        assignments = (
            Assignment.query.filter(
                Assignment.school_id == school_id,
                db.or_(
                    Assignment.teacher_id == (teacher_rec.id if teacher_rec else -1),
                    Assignment.class_id.in_(assigned_cids) if assigned_cids else False,
                ),
            )
            .order_by(Assignment.created_at.desc())
            .all()
        )
        announcements = (
            Announcement.query.filter(
                Announcement.school_id == school_id,
                db.or_(
                    Announcement.class_id.is_(None),
                    Announcement.class_id.in_(assigned_cids) if assigned_cids else False,
                ),
            )
            .order_by(Announcement.created_at.desc())
            .limit(20)
            .all()
        )
    else:
        visible_classes = all_classes
        visible_subjects = all_subjects
        class_subj_map = {c.id: [s.id for s in all_subjects] for c in all_classes}
        materials = Material.query.filter_by(school_id=school_id).order_by(Material.id.desc()).all()
        assignments = Assignment.query.filter_by(school_id=school_id).order_by(Assignment.created_at.desc()).all()
        announcements = Announcement.query.filter_by(school_id=school_id).order_by(Announcement.created_at.desc()).limit(20).all()

    return jsonify({
        "teacher": {
            "id": teacher_rec.id if teacher_rec else None,
            "staff_no": teacher_rec.staff_no if teacher_rec else current_user.username,
            "first_name": teacher_rec.first_name if teacher_rec else "Teacher",
            "last_name": teacher_rec.last_name if teacher_rec else "",
            "specialization": teacher_rec.subject_specialization if teacher_rec else None,
        },
        "classes": [{"id": c.id, "name": c.name, "capacity": c.capacity} for c in visible_classes],
        "subjects": [{"id": s.id, "name": s.name, "code": s.code} for s in visible_subjects],
        "class_subject_map": class_subj_map,
        "exams": [
            {
                "id": e.id,
                "name": e.name,
                "term_id": e.term_id,
                "start_date": e.start_date.isoformat() if e.start_date else (e.date.isoformat() if e.date else None),
                "end_date": e.end_date.isoformat() if e.end_date else (e.start_date.isoformat() if e.start_date else (e.date.isoformat() if e.date else None)),
                "date": e.date.isoformat() if e.date else (e.start_date.isoformat() if e.start_date else None),
                "venue": e.venue or "",
            }
            for e in all_exams
        ],
        "materials": [
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "filename": m.filename,
                "class_id": m.class_id,
                "class_name": class_map.get(m.class_id, "—"),
                "subject_id": m.subject_id,
                "subject_name": subj_map.get(m.subject_id, "—"),
                "file_size": getattr(m, "file_size", None),
                "is_archived": bool(getattr(m, "is_archived", False)),
                "is_author": bool(teacher_rec and m.teacher_id == teacher_rec.id),
            }
            for m in materials
        ],
        "assignments": [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "class_id": a.class_id,
                "class_name": class_map.get(a.class_id, "—"),
                "subject_id": a.subject_id,
                "subject_name": subj_map.get(a.subject_id, "—"),
                "assignment_date": a.assignment_date.isoformat() if getattr(a, "assignment_date", None) else None,
                "deadline": a.deadline.isoformat() if a.deadline else None,
                "has_attachment": bool(getattr(a, "attachment_path", None)),
                "attachment_name": getattr(a, "attachment_name", None),
                "attachment_type": getattr(a, "attachment_type", None),
                "submissions_count": Submission.query.filter_by(school_id=school_id, assignment_id=a.id).count(),
            }
            for a in assignments
        ],
        "announcements": [
            {
                "id": ann.id,
                "title": ann.title,
                "message": ann.message,
                "priority": getattr(ann, "priority", "Normal"),
                "created_at": ann.created_at.isoformat() if ann.created_at else None,
            }
            for ann in announcements
        ],
    })


@api.route("/teacher/attendance/<int:class_id>", methods=["GET", "POST"])
@login_required
def api_teacher_attendance(class_id):
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()
    school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()

    teacher_rec = None
    if current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not teacher_rec:
            return jsonify({"error": "No teacher profile found for your account."}), 403
        assigned_cids, _, _ = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
        if class_id not in assigned_cids:
            return jsonify({"error": "You are not authorized to record attendance for this class."}), 403

    students = Student.query.filter_by(school_id=school_id, class_id=class_id).order_by(Student.first_name.asc()).all()

    if request.method == "GET":
        date_str = request.args.get("date") or datetime.date.today().isoformat()
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            date_obj = datetime.date.today()

        existing_records = Attendance.query.filter_by(school_id=school_id, class_id=class_id, date=date_obj).all()
        already_recorded = len(existing_records) > 0
        existing = {a.student_id: a.status for a in existing_records}
        present_count = sum(1 for a in existing_records if a.status == "Present")
        absent_count = sum(1 for a in existing_records if a.status == "Absent")

        recorded_by_name = None
        updated_at_str = None
        if existing_records:
            first_rec = existing_records[0]
            if first_rec.recorded_by:
                recorded_by_name = f"{first_rec.recorded_by.first_name} {first_rec.recorded_by.last_name}"
            elif first_rec.recorded_by_id:
                u = db.session.get(User, first_rec.recorded_by_id)
                if u:
                    recorded_by_name = u.username
            if first_rec.updated_at:
                updated_at_str = first_rec.updated_at.isoformat()

        return jsonify({
            "class_id": school_class.id,
            "class_name": school_class.name,
            "date": date_obj.isoformat(),
            "already_recorded": already_recorded,
            "present_count": present_count,
            "absent_count": absent_count,
            "recorded_by_name": recorded_by_name,
            "updated_at": updated_at_str,
            "students": [
                {
                    "id": s.id,
                    "admission_no": s.admission_no,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "status": existing.get(s.id, "Present"),
                }
                for s in students
            ],
        })

    data = request.get_json(silent=True) or {}
    date_str = data.get("date") or datetime.date.today().isoformat()
    records = data.get("records") or {}
    allow_edit = bool(data.get("allow_edit", False))

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format."}), 400

    existing_count = Attendance.query.filter_by(school_id=school_id, class_id=class_id, date=date_obj).count()
    if existing_count > 0 and not allow_edit:
        return jsonify({
            "error": "Attendance has already been recorded for this class on this date. Please unlock edit mode to make changes.",
            "already_recorded": True,
        }), 409

    now_utc = utc_now()
    present_c = 0
    absent_c = 0
    for s in students:
        status = records.get(str(s.id)) or records.get(s.id) or "Present"
        if status not in ("Present", "Absent"):
            status = "Present"
        if status == "Present":
            present_c += 1
        else:
            absent_c += 1

        rec = Attendance.query.filter_by(school_id=school_id, student_id=s.id, date=date_obj).first()
        if rec:
            rec.status = status
            rec.recorded_by_id = teacher_rec.id if teacher_rec else current_user.id
            rec.updated_at = now_utc
        else:
            db.session.add(
                Attendance(
                    school_id=school_id,
                    student_id=s.id,
                    class_id=class_id,
                    date=date_obj,
                    status=status,
                    recorded_by_id=teacher_rec.id if teacher_rec else current_user.id,
                    updated_at=now_utc,
                )
            )

    action_label = "updated" if existing_count > 0 else "saved"
    record_activity(
        "attendance",
        "attendance_recorded",
        f"Attendance register {action_label} for {school_class.name} ({date_obj.isoformat()}) — {present_c} present, {absent_c} absent.",
        school_id=school_id,
        target_type="class",
        target_id=school_class.name,
        commit=False,
    )
    db.session.commit()
    return jsonify({
        "message": f"Attendance register {action_label} for {school_class.name} ({date_obj.isoformat()}).",
        "already_recorded": True,
        "present_count": present_c,
        "absent_count": absent_c,
    })


@api.route("/teacher/assignments", methods=["POST"])
@login_required
def api_teacher_create_assignment():
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.form if request.form else (request.get_json(silent=True) or {})

    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    class_id = data.get("class_id")
    subject_id = data.get("subject_id")
    assignment_date_str = data.get("assignment_date")
    due_date = data.get("due_date") or data.get("deadline")

    if not all([title, description, class_id, subject_id, due_date]):
        return jsonify({"error": "Title, description, class, subject, and due date are required."}), 400

    try:
        class_id = int(class_id)
        subject_id = int(subject_id)
        due_dt = datetime.datetime.strptime(due_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid class, subject, or due date."}), 400

    assignment_date = datetime.date.today()
    if assignment_date_str:
        try:
            assignment_date = datetime.datetime.strptime(assignment_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
        return jsonify({"error": "Invalid class."}), 404
    if not Subject.query.filter_by(id=subject_id, school_id=school_id).first():
        return jsonify({"error": "Invalid subject."}), 404

    teacher_rec = None
    if current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not teacher_rec:
            return jsonify({"error": "No teacher profile found for your account."}), 403
        assigned_cids, assigned_sids, class_subj_map = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
        if class_id not in assigned_cids:
            return jsonify({"error": "You are not authorized to create assignments for this class."}), 403
        class_subjects = class_subj_map.get(class_id, [])
        if class_subjects and subject_id not in class_subjects:
            return jsonify({"error": "You are not assigned to teach this subject in this class."}), 403

    # File attachment processing (up to 10MB)
    attachment_path = None
    attachment_name = None
    attachment_type = None

    uploaded_file = request.files.get("file") or request.files.get("attachment")
    if uploaded_file and uploaded_file.filename:
        if not allowed_file(uploaded_file.filename):
            return jsonify({"error": "Attachment type not allowed. Supported types: PDF, DOC, DOCX, PNG, JPG, TXT."}), 400

        uploaded_file.seek(0, os.SEEK_END)
        file_length = uploaded_file.tell()
        uploaded_file.seek(0)
        if file_length > 10 * 1024 * 1024:
            return jsonify({"error": "Attachment file size exceeds the 10 MB limit."}), 400

        clean_orig = secure_filename(uploaded_file.filename)
        filename = f"assign_{school_id}_{int(utc_now().timestamp())}_{clean_orig}"
        save_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "assignments")
        os.makedirs(save_dir, exist_ok=True)
        uploaded_file.save(os.path.join(save_dir, filename))

        attachment_path = f"assignments/{filename}"
        attachment_name = uploaded_file.filename
        attachment_type = uploaded_file.filename.rsplit(".", 1)[1].lower() if "." in uploaded_file.filename else "unknown"

    a = Assignment(
        school_id=school_id,
        title=title,
        description=description,
        class_id=class_id,
        subject_id=subject_id,
        teacher_id=teacher_rec.id if teacher_rec else None,
        assignment_date=assignment_date,
        deadline=due_dt,
        attachment_path=attachment_path,
        attachment_name=attachment_name,
        attachment_type=attachment_type,
    )
    db.session.add(a)
    record_activity(
        "assignment",
        "assignment_created",
        f"Assignment '{title}' created for class ID {class_id}.",
        school_id=school_id,
        target_type="assignment",
        target_id=title,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": "Assignment created successfully.", "id": a.id}), 201


@api.route("/assignments/<int:assignment_id>/attachment", methods=["GET"])
@login_required
def api_download_assignment_attachment(assignment_id: int):
    school_id = get_current_school_id()
    assignment = Assignment.query.filter_by(id=assignment_id, school_id=school_id).first_or_404()
    if not assignment.attachment_path:
        return jsonify({"error": "No attachment for this assignment."}), 404

    authorized = False
    if current_user.role == "admin":
        authorized = True
    elif current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if teacher_rec:
            assigned_cids, _, _ = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
            if assignment.class_id in assigned_cids or assignment.teacher_id == teacher_rec.id:
                authorized = True
    elif current_user.role == "student":
        student_rec = Student.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not student_rec:
            student_rec = Student.query.filter_by(school_id=school_id, admission_no=current_user.username).first()
        if student_rec and student_rec.class_id == assignment.class_id:
            authorized = True
    elif current_user.role == "parent":
        parent_rec = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if parent_rec:
            links = ParentStudent.query.filter_by(school_id=school_id, parent_id=parent_rec.id).all()
            for lk in links:
                if lk.student and lk.student.class_id == assignment.class_id:
                    authorized = True
                    break

    if not authorized:
        return jsonify({"error": "You are not authorized to download this assignment attachment."}), 403

    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], assignment.attachment_path)
    if not os.path.exists(filepath):
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(assignment.attachment_path))
    if not os.path.exists(filepath):
        return jsonify({"error": "Attachment file not found on disk."}), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=assignment.attachment_name or os.path.basename(filepath),
    )


@api.route("/teacher/submissions/<int:assignment_id>", methods=["GET"])
@login_required
def api_teacher_submissions(assignment_id):
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()
    assignment = Assignment.query.filter_by(id=assignment_id, school_id=school_id).first_or_404()
    subs = Submission.query.filter_by(school_id=school_id, assignment_id=assignment_id).all()
    student_map = {
        s.id: f"{s.first_name} {s.last_name} ({s.admission_no})"
        for s in Student.query.filter_by(school_id=school_id).all()
    }
    return jsonify({
        "assignment": {"id": assignment.id, "title": assignment.title},
        "submissions": [
            {
                "id": sub.id,
                "student_id": sub.student_id,
                "student_name": student_map.get(sub.student_id, "—"),
                "file_path": sub.file_path,
                "marks": sub.marks,
                "feedback": sub.feedback,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
            }
            for sub in subs
        ],
    })


@api.route("/teacher/grade/<int:submission_id>", methods=["POST"])
@login_required
def api_teacher_grade_submission(submission_id):
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()
    sub = Submission.query.filter_by(id=submission_id, school_id=school_id).first_or_404()
    data = request.get_json(silent=True) or request.form
    try:
        marks = float(data.get("marks"))
    except (ValueError, TypeError):
        return jsonify({"error": "Valid numeric marks are required."}), 400
    feedback = (data.get("feedback") or "").strip()
    sub.marks = marks
    sub.feedback = feedback
    db.session.commit()
    return jsonify({"message": "Submission graded successfully."})


@api.route("/teacher/results/<int:class_id>/<int:subject_id>/<int:exam_id>", methods=["GET", "POST"])
@login_required
def api_teacher_results(class_id, subject_id, exam_id):
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()

    if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
        return jsonify({"error": "Invalid class."}), 404
    subject = Subject.query.filter_by(id=subject_id, school_id=school_id).first_or_404()
    exam = Exam.query.filter_by(id=exam_id, school_id=school_id).first_or_404()

    if current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not teacher_rec:
            return jsonify({"error": "No teacher profile found for your account."}), 403
        assigned_cids, assigned_sids, class_subj_map = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
        if class_id not in assigned_cids:
            return jsonify({"error": "You are not authorized to enter marks for this class."}), 403
        class_subjects = class_subj_map.get(class_id, [])
        if class_subjects and subject_id not in class_subjects:
            return jsonify({"error": "You are not assigned to teach this subject in this class."}), 403

    students = Student.query.filter_by(school_id=school_id, class_id=class_id).order_by(Student.first_name.asc()).all()

    if request.method == "GET":
        existing = {
            r.student_id: r.marks
            for r in Result.query.filter_by(school_id=school_id, subject_id=subject_id, exam_id=exam_id).all()
        }
        return jsonify({
            "subject_name": subject.name,
            "exam_name": exam.name,
            "students": [
                {
                    "id": s.id,
                    "admission_no": s.admission_no,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "marks": existing.get(s.id, ""),
                    "grade": calculate_grade(existing[s.id]) if s.id in existing else "—",
                }
                for s in students
            ],
        })

    data = request.get_json(silent=True) or {}
    marks_map = data.get("marks") or {}
    saved_count = 0

    for s in students:
        raw_val = marks_map.get(str(s.id), marks_map.get(s.id))
        if raw_val is None or raw_val == "":
            continue
        try:
            score = float(raw_val)
        except (ValueError, TypeError):
            continue
        if score < 0 or score > 100:
            return jsonify({"error": f"Marks for {s.first_name} must be between 0 and 100."}), 400

        existing_res = Result.query.filter_by(
            school_id=school_id, student_id=s.id, subject_id=subject_id, exam_id=exam_id
        ).first()
        if existing_res:
            existing_res.marks = score
        else:
            db.session.add(
                Result(
                    school_id=school_id,
                    student_id=s.id,
                    subject_id=subject_id,
                    exam_id=exam_id,
                    marks=score,
                )
            )
        saved_count += 1

    record_activity(
        "exam",
        "results_recorded",
        f"Examination results updated for {subject.name} ({exam.name}) — {saved_count} student record(s).",
        school_id=school_id,
        target_type="exam",
        target_id=exam.name,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": f"Saved exam marks for {saved_count} student(s)."})


@api.route("/teacher/materials", methods=["POST"])
@login_required
def api_teacher_upload_material():
    err = _require_role("teacher", "admin")
    if err:
        return err
    school_id = get_current_school_id()
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    class_id = request.form.get("class_id")
    subject_id = request.form.get("subject_id")
    term_id = request.form.get("term_id")
    file = request.files.get("file")

    if not all([title, description, class_id, subject_id, file]) or not file.filename:
        return jsonify({"error": "Title, description, class, subject, and file are required."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed."}), 400

    try:
        class_id = int(class_id)
        subject_id = int(subject_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid class or subject."}), 400

    term_id_int = None
    if term_id:
        try:
            term_id_int = int(term_id)
        except (ValueError, TypeError):
            pass

    if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
        return jsonify({"error": "Invalid class."}), 404
    if not Subject.query.filter_by(id=subject_id, school_id=school_id).first():
        return jsonify({"error": "Invalid subject."}), 404

    teacher_rec = None
    if current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not teacher_rec:
            return jsonify({"error": "No teacher profile found for your account."}), 403
        assigned_cids, assigned_sids, class_subj_map = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
        if class_id not in assigned_cids:
            return jsonify({"error": "You are not authorized to upload materials for this class."}), 403
        class_subjects = class_subj_map.get(class_id, [])
        if class_subjects and subject_id not in class_subjects:
            return jsonify({"error": "You are not assigned to teach this subject in this class."}), 403

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > 15 * 1024 * 1024:
        return jsonify({"error": "Study material exceeds the 15 MB limit."}), 400

    filename = f"{school_id}_{int(utc_now().timestamp())}_{secure_filename(file.filename)}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

    mat = Material(
        school_id=school_id,
        title=title,
        description=description,
        filename=filename,
        teacher_id=teacher_rec.id if teacher_rec else None,
        class_id=class_id,
        subject_id=subject_id,
        term_id=term_id_int,
        file_size=file_size,
        is_archived=False,
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify({"message": "Study material uploaded successfully.", "id": mat.id}), 201


@api.route("/materials/<int:material_id>/download", methods=["GET"])
@login_required
def api_download_material(material_id: int):
    school_id = get_current_school_id()
    mat = Material.query.filter_by(id=material_id, school_id=school_id).first_or_404()

    authorized = False
    if current_user.role == "admin":
        authorized = True
    elif current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if teacher_rec:
            assigned_cids, _, _ = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
            if mat.class_id in assigned_cids or mat.teacher_id == teacher_rec.id:
                authorized = True
    elif current_user.role == "student":
        student_rec = Student.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not student_rec:
            student_rec = Student.query.filter_by(school_id=school_id, admission_no=current_user.username).first()
        if student_rec and student_rec.class_id == mat.class_id:
            authorized = True
    elif current_user.role == "parent":
        parent_rec = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if parent_rec:
            links = ParentStudent.query.filter_by(school_id=school_id, parent_id=parent_rec.id).all()
            for lk in links:
                if lk.student and lk.student.class_id == mat.class_id:
                    authorized = True
                    break

    if not authorized:
        return jsonify({"error": "You are not authorized to download this study material."}), 403

    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], mat.filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Material file not found on disk."}), 404

    return send_file(filepath, as_attachment=True, download_name=mat.filename)


@api.route("/materials/<int:material_id>/archive", methods=["POST"])
@login_required
def api_archive_material(material_id: int):
    school_id = get_current_school_id()
    mat = Material.query.filter_by(id=material_id, school_id=school_id).first_or_404()

    if current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not teacher_rec or (mat.teacher_id != teacher_rec.id and mat.teacher_id is not None):
            return jsonify({"error": "Only the authoring teacher or administrator can archive this material."}), 403
    elif current_user.role != "admin":
        return jsonify({"error": "Unauthorized."}), 403

    data = request.get_json(silent=True) or {}
    new_status = data.get("is_archived")
    if new_status is None:
        mat.is_archived = not bool(mat.is_archived)
    else:
        mat.is_archived = bool(new_status)

    db.session.commit()
    return jsonify({
        "message": f"Material '{mat.title}' has been {'archived' if mat.is_archived else 'restored'}.",
        "is_archived": mat.is_archived,
    })


# ══════════════════════════════════════════════════════════════════
#  STUDENT PORTAL
# ══════════════════════════════════════════════════════════════════

@api.route("/student/overview", methods=["GET"])
@login_required
def api_student_overview():
    err = _require_role("student")
    if err:
        return err
    school_id = get_current_school_id()
    stu = None
    if current_user.student_id:
        stu = Student.query.filter_by(id=current_user.student_id, school_id=school_id).first()
    if not stu:
        stu = Student.query.filter_by(school_id=school_id, admission_no=current_user.username).first()
    if not stu:
        return jsonify({"error": "Student profile not found."}), 404

    school_class = SchoolClass.query.filter_by(id=stu.class_id, school_id=school_id).first()
    terms = Term.query.filter_by(school_id=school_id).all()
    results = Result.query.filter_by(school_id=school_id, student_id=stu.id).all()
    materials = Material.query.filter_by(school_id=school_id, class_id=stu.class_id).all()
    assignments = (
        Assignment.query.filter_by(school_id=school_id, class_id=stu.class_id)
        .order_by(Assignment.created_at.desc())
        .all()
    )
    submissions = {
        sub.assignment_id: sub
        for sub in Submission.query.filter_by(school_id=school_id, student_id=stu.id).all()
    }
    payments = (
        Payment.query.filter_by(school_id=school_id, student_id=stu.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )
    announcements = (
        Announcement.query.filter(
            Announcement.school_id == school_id,
            db.or_(Announcement.class_id == stu.class_id, Announcement.class_id.is_(None)),
        )
        .order_by(Announcement.created_at.desc())
        .limit(15)
        .all()
    )
    timetable = Timetable.query.filter_by(school_id=school_id, class_id=stu.class_id).all()
    subj_map = {s.id: s.name for s in Subject.query.filter_by(school_id=school_id).all()}
    term_map = {t.id: t.name for t in terms}

    return jsonify({
        "student": {
            "id": stu.id,
            "admission_no": stu.admission_no,
            "first_name": stu.first_name,
            "last_name": stu.last_name,
            "gender": stu.gender,
            "class_id": stu.class_id,
            "class_name": school_class.name if school_class else "—",
        },
        "fee_balances": [
            {
                "term_id": t.id,
                "term_name": t.name,
                "balance": calculate_balance(stu.id, t.id, school_id),
            }
            for t in terms
        ],
        "payments": [
            {
                "id": p.id,
                "term_name": term_map.get(p.term_id, "—"),
                "amount_paid": p.amount_paid,
                "currency": p.currency or "ZMW",
                "reference": p.reference,
                "lipila_reference_id": p.lipila_reference_id,
                "payment_method": p.payment_method or "manual",
                "status": p.status or "completed",
                "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            }
            for p in payments
        ],
        "results": [
            {
                "id": r.id,
                "subject": r.subject.name if r.subject else subj_map.get(r.subject_id, "—"),
                "exam": r.exam.name if r.exam else "Exam",
                "term_id": r.exam.term_id if r.exam else None,
                "marks": r.marks,
                "grade": calculate_grade(r.marks),
            }
            for r in results
        ],
        "assignments": [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "subject_name": subj_map.get(a.subject_id, "—"),
                "assignment_date": a.assignment_date.isoformat() if getattr(a, "assignment_date", None) else None,
                "deadline": a.deadline.isoformat() if a.deadline else None,
                "has_attachment": bool(getattr(a, "attachment_path", None)),
                "attachment_name": getattr(a, "attachment_name", None),
                "attachment_type": getattr(a, "attachment_type", None),
                "submitted": a.id in submissions,
                "marks": submissions[a.id].marks if a.id in submissions else None,
                "feedback": submissions[a.id].feedback if a.id in submissions else None,
            }
            for a in assignments
        ],
        "materials": [
            {
                "id": m.id,
                "title": m.title,
                "description": m.description,
                "filename": m.filename,
                "file_size": getattr(m, "file_size", None),
                "subject_name": subj_map.get(m.subject_id, "—"),
            }
            for m in materials
            if not getattr(m, "is_archived", False)
        ],
        "announcements": [
            {
                "id": ann.id,
                "title": ann.title,
                "message": ann.message,
                "created_at": ann.created_at.isoformat() if ann.created_at else None,
            }
            for ann in announcements
        ],
        "timetable": [
            {
                "id": tt.id,
                "day": tt.day,
                "start_time": tt.start_time,
                "end_time": tt.end_time,
                "subject_name": subj_map.get(tt.subject_id, "—"),
            }
            for tt in timetable
        ],
    })


@api.route("/student/submit/<int:assignment_id>", methods=["POST"])
@login_required
def api_student_submit_assignment(assignment_id):
    err = _require_role("student")
    if err:
        return err
    school_id = get_current_school_id()
    stu = Student.query.filter_by(school_id=school_id, admission_no=current_user.username).first_or_404()
    assignment = Assignment.query.filter_by(id=assignment_id, school_id=school_id, class_id=stu.class_id).first_or_404()
    file = request.files.get("file")

    if not file or not file.filename:
        return jsonify({"error": "Please choose a file to upload."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed."}), 400

    filename = f"{school_id}_{stu.id}_{int(utc_now().timestamp())}_{secure_filename(file.filename)}"
    file.save(os.path.join(current_app.config["ASSIGNMENT_UPLOAD"], filename))

    sub = Submission(
        school_id=school_id,
        assignment_id=assignment.id,
        student_id=stu.id,
        file_path=filename,
    )
    db.session.add(sub)
    record_activity(
        "academic",
        "assignment_submitted",
        f"Assignment '{assignment.title}' submitted by {stu.admission_no}.",
        school_id=school_id,
        status="success",
        target_type="assignment",
        target_id=assignment.title,
        commit=False,
    )
    db.session.commit()
    return jsonify({"message": "Assignment submitted successfully."}), 201


# ══════════════════════════════════════════════════════════════════
#  PARENT PORTAL
# ══════════════════════════════════════════════════════════════════

@api.route("/parent/overview", methods=["GET"])
@login_required
def api_parent_overview():
    err = _require_role("parent")
    if err:
        return err
    school_id = get_current_school_id()
    p = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
    links = ParentStudent.query.filter_by(school_id=school_id, parent_id=p.id).all() if p else []
    children = [link.student for link in links if link.student and link.student.school_id == school_id]

    terms = Term.query.filter_by(school_id=school_id).all()
    term_map = {t.id: t.name for t in terms}
    class_map = {c.id: c.name for c in SchoolClass.query.filter_by(school_id=school_id).all()}
    subj_map = {s.id: s.name for s in Subject.query.filter_by(school_id=school_id).all()}

    children_payload = []
    class_ids = []
    for child in children:
        if child.class_id:
            class_ids.append(child.class_id)
        results = Result.query.filter_by(school_id=school_id, student_id=child.id).all()
        att_records = (
            Attendance.query.filter_by(school_id=school_id, student_id=child.id)
            .order_by(Attendance.date.desc())
            .limit(30)
            .all()
        )
        payments = (
            Payment.query.filter_by(school_id=school_id, student_id=child.id)
            .order_by(Payment.payment_date.desc())
            .all()
        )
        child_exams = (
            Exam.query.filter(
                Exam.school_id == school_id,
                db.or_(Exam.class_id == child.class_id, Exam.class_id.is_(None)),
            )
            .order_by(Exam.date.desc())
            .all()
        )
        child_assignments = (
            Assignment.query.filter_by(school_id=school_id, class_id=child.class_id)
            .order_by(Assignment.created_at.desc())
            .all()
        )
        child_materials = (
            Material.query.filter_by(school_id=school_id, class_id=child.class_id)
            .order_by(Material.id.desc())
            .all()
        )
        children_payload.append({
            "id": child.id,
            "admission_no": child.admission_no,
            "first_name": child.first_name,
            "last_name": child.last_name,
            "gender": child.gender,
            "class_id": child.class_id,
            "class_name": class_map.get(child.class_id, "—"),
            "exams": [
                {
                    "id": ex.id,
                    "name": ex.name,
                    "term_name": term_map.get(ex.term_id, "—"),
                    "start_date": ex.start_date.isoformat() if ex.start_date else (ex.date.isoformat() if ex.date else None),
                    "end_date": ex.end_date.isoformat() if ex.end_date else (ex.start_date.isoformat() if ex.start_date else (ex.date.isoformat() if ex.date else None)),
                    "date": ex.date.isoformat() if ex.date else (ex.start_date.isoformat() if ex.start_date else None),
                    "start_time": ex.start_time or "",
                    "end_time": ex.end_time or "",
                    "venue": ex.venue or "",
                    "exam_type": ex.exam_type or "Main",
                }
                for ex in child_exams
            ],
            "assignments": [
                {
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "subject_name": subj_map.get(a.subject_id, "—"),
                    "assignment_date": a.assignment_date.isoformat() if getattr(a, "assignment_date", None) else None,
                    "deadline": a.deadline.isoformat() if a.deadline else None,
                    "has_attachment": bool(getattr(a, "attachment_path", None)),
                    "attachment_name": getattr(a, "attachment_name", None),
                    "attachment_type": getattr(a, "attachment_type", None),
                }
                for a in child_assignments
            ],
            "materials": [
                {
                    "id": m.id,
                    "title": m.title,
                    "description": m.description,
                    "filename": m.filename,
                    "file_size": getattr(m, "file_size", None),
                    "subject_name": subj_map.get(m.subject_id, "—"),
                }
                for m in child_materials
                if not getattr(m, "is_archived", False)
            ],
            "fee_balances": [
                {
                    "term_id": t.id,
                    "term_name": t.name,
                    "balance": calculate_balance(child.id, t.id, school_id),
                }
                for t in terms
            ],
            "results": [
                {
                    "id": r.id,
                    "subject": r.subject.name if r.subject else subj_map.get(r.subject_id, "—"),
                    "exam": r.exam.name if r.exam else "Exam",
                    "term_id": r.exam.term_id if r.exam else None,
                    "marks": r.marks,
                    "grade": calculate_grade(r.marks),
                }
                for r in results
            ],
            "attendance": [
                {
                    "id": a.id,
                    "date": a.date.isoformat() if a.date else None,
                    "status": a.status,
                }
                for a in att_records
            ],
            "payments": [
                {
                    "id": pay.id,
                    "term_name": term_map.get(pay.term_id, "—"),
                    "amount_paid": pay.amount_paid,
                    "currency": pay.currency or "ZMW",
                    "reference": pay.reference,
                    "lipila_reference_id": pay.lipila_reference_id,
                    "payment_method": pay.payment_method or "manual",
                    "status": pay.status or "completed",
                    "payment_date": pay.payment_date.isoformat() if pay.payment_date else None,
                }
                for pay in payments
            ],
        })

    announcements = (
        Announcement.query.filter(
            Announcement.school_id == school_id,
            db.or_(
                Announcement.class_id.in_(class_ids) if class_ids else False,
                Announcement.class_id.is_(None),
            ),
        )
        .order_by(Announcement.created_at.desc())
        .limit(15)
        .all()
    )

    return jsonify({
        "parent": {
            "id": p.id if p else None,
            "first_name": p.first_name if p else current_user.username,
            "last_name": p.last_name if p else "",
            "phone": p.phone if p else None,
        },
        "children": children_payload,
        "announcements": [
            {
                "id": ann.id,
                "title": ann.title,
                "message": ann.message,
                "created_at": ann.created_at.isoformat() if ann.created_at else None,
            }
            for ann in announcements
        ],
    })


# ══════════════════════════════════════════════════════════════════
#  BILLING, LIPILA CHECKOUTS, SANDBOX SIMULATOR & RECEIPTS
# ══════════════════════════════════════════════════════════════════

@api.route("/billing/plans", methods=["GET"])
@login_required
def api_billing_plans():
    school_id = get_current_school_id()
    school = School.query.filter_by(id=school_id, is_active=True).first_or_404()
    subs = (
        Subscription.query.filter_by(school_id=school.id)
        .order_by(Subscription.created_at.desc())
        .limit(15)
        .all()
    )
    client = LipilaClient()
    return jsonify({
        "school": _serialize_school(school),
        "prices": current_app.config["PLAN_PRICES"],
        "limits": current_app.config["PLAN_LIMITS"],
        "features": current_app.config["PLAN_FEATURES"],
        "simulator_mode": client.simulator_enabled,
        "subscriptions": [
            {
                "id": s.id,
                "plan": s.plan,
                "billing_cycle": s.billing_cycle,
                "amount": s.amount,
                "currency": s.currency,
                "payment_method": s.payment_method,
                "lipila_reference_id": s.lipila_reference_id,
                "status": s.status,
                "is_sandbox_simulated": s.is_sandbox_simulated,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in subs
        ],
    })


@api.route("/billing/checkout-subscription", methods=["POST"])
@login_required
def api_checkout_subscription():
    err = _require_role("admin")
    if err:
        return err
    school_id = get_current_school_id()
    school = School.query.filter_by(id=school_id, is_active=True).first_or_404()
    data = request.get_json(silent=True) or request.form

    plan = (data.get("plan") or "").strip().lower()
    cycle = (data.get("cycle") or "monthly").strip().lower()
    payment_method = (data.get("payment_method") or "mobile_money").strip().lower()
    phone_number = (data.get("phone_number") or school.phone or "").strip()

    prices = current_app.config["PLAN_PRICES"]
    if plan not in prices or plan == "free" or cycle not in ("monthly", "yearly"):
        return jsonify({"error": "Invalid plan or billing cycle."}), 400
    if payment_method not in ("mobile_money", "card"):
        return jsonify({"error": "Please select Mobile Money or Card payment."}), 400

    amount_key = "amount_yearly" if cycle == "yearly" else "amount_monthly"
    amount = float(prices[plan].get(amount_key, 0))
    currency = prices[plan].get("currency", "ZMW")

    client = LipilaClient()
    reference_id = client.generate_reference("SUB")

    sub = Subscription(
        school_id=school.id,
        lipila_reference_id=reference_id,
        payment_method=payment_method,
        account_number=normalize_zambia_phone(phone_number) if phone_number else None,
        plan=plan,
        billing_cycle=cycle,
        amount=amount,
        currency=currency,
        status="pending",
        is_sandbox_simulated=client.simulator_enabled,
    )
    db.session.add(sub)
    record_activity(
        "subscription",
        "subscription_initiated",
        f"Subscription checkout initiated for {plan.title()} ({cycle}) — K{amount:.2f} via {payment_method} ({reference_id}).",
        school_id=school.id,
        status="pending",
        target_type="subscription",
        target_id=reference_id,
        commit=False,
    )
    db.session.commit()

    callback_url = current_app.config.get("LIPILA_CALLBACK_URL") or request.host_url.rstrip("/") + "/billing/webhook/lipila"
    back_url = request.host_url.rstrip("/") + f"/billing/status/{reference_id}"
    narration = f"EduManage {plan.title()} ({cycle}) - {school.name}"

    try:
        if payment_method == "mobile_money":
            res = client.initiate_mobile_money_collection(
                reference_id=reference_id,
                amount=amount,
                phone_number=phone_number,
                narration=narration,
                email=school.email,
                callback_url=callback_url,
            )
        else:
            res = client.initiate_card_collection(
                reference_id=reference_id,
                amount=amount,
                narration=narration,
                customer={
                    "firstName": school.name[:30],
                    "lastName": "School",
                    "email": school.email,
                    "phoneNumber": phone_number or "0977000000",
                    "country": "ZM",
                    "city": "Lusaka",
                    "address": school.address or "Lusaka, Zambia",
                },
                back_url=back_url,
                callback_url=callback_url,
                currency=currency,
            )
    except LipilaError as exc:
        sub.status = "failed"
        db.session.commit()
        return jsonify({"error": str(exc)}), 400

    sub.lipila_transaction_id = res.get("transaction_id")
    db.session.commit()

    return jsonify({
        "reference_id": reference_id,
        "status": sub.status,
        "simulator": bool(res.get("simulator")),
        "redirect_url": res.get("redirect_url"),
    })


@api.route("/billing/checkout-fee", methods=["POST"])
@login_required
def api_checkout_fee():
    data = request.get_json(silent=True) or request.form
    try:
        student_id = int(data.get("student_id"))
        term_id = int(data.get("term_id"))
        amount = round(float(data.get("amount")), 2)
    except (ValueError, TypeError):
        return jsonify({"error": "Valid student, term, and ZMW amount are required."}), 400

    student, school = _authorize_student_fee_access(student_id)
    term = Term.query.filter_by(id=term_id, school_id=school.id).first_or_404()
    balance = calculate_balance(student.id, term.id, school.id)

    if amount <= 0:
        return jsonify({"error": "Payment amount must be greater than K0.00."}), 400
    if balance > 0 and amount > balance:
        return jsonify({"error": f"Amount cannot exceed outstanding balance of K{balance:.2f}."}), 400

    payment_method = (data.get("payment_method") or "mobile_money").strip().lower()
    phone_number = (data.get("phone_number") or "").strip()
    if payment_method not in ("mobile_money", "card"):
        return jsonify({"error": "Please select Mobile Money or Card payment."}), 400

    client = LipilaClient()
    reference_id = client.generate_reference("FEE")

    payment = Payment(
        school_id=school.id,
        student_id=student.id,
        term_id=term.id,
        amount_paid=amount,
        currency="ZMW",
        reference=None,
        bank_reference=None,
        lipila_reference_id=reference_id,
        payment_method=payment_method,
        account_number=normalize_zambia_phone(phone_number) if phone_number else None,
        status="pending",
        is_sandbox_simulated=client.simulator_enabled,
        narration=f"School Fees - {student.first_name} {student.last_name} ({student.admission_no}) - {term.name}",
    )
    db.session.add(payment)
    record_activity(
        "payment",
        "fee_payment_initiated",
        f"School fee payment initiated ({student.admission_no}) — K{amount:.2f} via {payment_method} ({reference_id}).",
        school_id=school.id,
        status="pending",
        target_type="payment",
        target_id=reference_id,
        commit=False,
    )
    db.session.commit()

    callback_url = current_app.config.get("LIPILA_CALLBACK_URL") or request.host_url.rstrip("/") + "/billing/webhook/lipila"
    back_url = request.host_url.rstrip("/") + f"/billing/status/{reference_id}"

    try:
        if payment_method == "mobile_money":
            res = client.initiate_mobile_money_collection(
                reference_id=reference_id,
                amount=amount,
                phone_number=phone_number,
                narration=payment.narration,
                email=current_user.email or school.email,
                callback_url=callback_url,
            )
        else:
            res = client.initiate_card_collection(
                reference_id=reference_id,
                amount=amount,
                narration=payment.narration,
                customer={
                    "firstName": student.first_name,
                    "lastName": student.last_name,
                    "email": current_user.email or school.email,
                    "phoneNumber": phone_number or school.phone or "0977000000",
                    "country": "ZM",
                    "city": "Lusaka",
                    "address": school.address or "Lusaka, Zambia",
                },
                back_url=back_url,
                callback_url=callback_url,
                currency="ZMW",
            )
    except LipilaError as exc:
        payment.status = "failed"
        db.session.commit()
        return jsonify({"error": str(exc)}), 400

    payment.lipila_transaction_id = res.get("transaction_id")
    db.session.commit()

    return jsonify({
        "reference_id": reference_id,
        "status": payment.status,
        "simulator": bool(res.get("simulator")),
        "redirect_url": res.get("redirect_url"),
    })


@api.route("/billing/status/<reference_id>", methods=["GET", "POST"])
@login_required
def api_billing_status(reference_id):
    school_id = get_current_school_id()
    sub = Subscription.query.filter_by(lipila_reference_id=reference_id, school_id=school_id).first()
    payment = None
    if not sub:
        payment = Payment.query.filter_by(lipila_reference_id=reference_id, school_id=school_id).first()

    if not sub and not payment:
        return jsonify({"error": "Transaction not found."}), 404

    client = LipilaClient()
    record = sub or payment

    if record.status == "pending" and not client.simulator_enabled:
        try:
            status_res = client.check_collection_status(reference_id)
            if status_res["status"] in ("completed", "failed"):
                if sub:
                    _settle_subscription(sub, status_res["status"], status_res.get("transaction_id"), is_simulated=False)
                else:
                    _settle_fee_payment(payment, status_res["status"], status_res.get("transaction_id"), is_simulated=False)
        except LipilaError:
            pass

    if sub:
        return jsonify({
            "kind": "subscription",
            "reference_id": sub.lipila_reference_id,
            "transaction_id": sub.lipila_transaction_id,
            "status": sub.status,
            "amount": sub.amount,
            "currency": sub.currency,
            "payment_method": sub.payment_method,
            "account_number": sub.account_number,
            "plan": sub.plan,
            "billing_cycle": sub.billing_cycle,
            "is_sandbox": sub.is_sandbox_simulated or client.simulator_enabled,
            "receipt_id": None,
            "receipt_ref": None,
        })

    student = Student.query.filter_by(id=payment.student_id, school_id=school_id).first()
    term = Term.query.filter_by(id=payment.term_id, school_id=school_id).first()
    return jsonify({
        "kind": "fee",
        "reference_id": payment.lipila_reference_id,
        "transaction_id": payment.lipila_transaction_id,
        "status": payment.status,
        "amount": payment.amount_paid,
        "currency": payment.currency or "ZMW",
        "payment_method": payment.payment_method,
        "account_number": payment.account_number,
        "student_id": payment.student_id,
        "student_name": f"{student.first_name} {student.last_name}" if student else "—",
        "term_name": term.name if term else "—",
        "is_sandbox": payment.is_sandbox_simulated or client.simulator_enabled,
        "receipt_id": payment.id if payment.status == "completed" else None,
        "receipt_ref": payment.reference if payment.status == "completed" else None,
    })


@api.route("/billing/sandbox/<reference_id>", methods=["POST"])
@login_required
def api_billing_sandbox_action(reference_id):
    if current_app.config.get("IS_PRODUCTION"):
        return jsonify({"error": "Sandbox simulator is disabled in production."}), 403

    client = LipilaClient()
    if not client.simulator_enabled:
        return jsonify({"error": "Sandbox simulator is disabled."}), 403

    school_id = get_current_school_id()
    sub = Subscription.query.filter_by(lipila_reference_id=reference_id, school_id=school_id).first()
    payment = None
    if not sub:
        payment = Payment.query.filter_by(lipila_reference_id=reference_id, school_id=school_id).first()
    if not sub and not payment:
        return jsonify({"error": "Transaction not found."}), 404

    data = request.get_json(silent=True) or request.form
    action = (data.get("action") or "").strip().lower()
    sim_tx_id = f"SIM-TX-{reference_id[-10:]}"

    if action == "approve":
        if sub:
            _settle_subscription(sub, "completed", transaction_id=sim_tx_id, is_simulated=True)
        else:
            _settle_fee_payment(payment, "completed", transaction_id=sim_tx_id, is_simulated=True)
    elif action == "decline":
        if sub:
            _settle_subscription(sub, "failed", transaction_id=sim_tx_id, is_simulated=True)
        else:
            _settle_fee_payment(payment, "failed", transaction_id=sim_tx_id, is_simulated=True)

    return api_billing_status(reference_id)


@api.route("/billing/receipt/<int:payment_id>", methods=["GET"])
@login_required
def api_billing_receipt(payment_id):
    school_id = get_current_school_id()
    payment = Payment.query.filter_by(id=payment_id, school_id=school_id).first_or_404()

    if payment.status not in ("completed", None):
        return jsonify({"error": "Receipt is only available after payment is confirmed."}), 403

    if current_user.role == "student":
        own = Student.query.filter_by(school_id=school_id, admission_no=current_user.username).first()
        if (not own or own.id != payment.student_id) and current_user.student_id != payment.student_id:
            return jsonify({"error": "Unauthorized access to receipt."}), 403
    elif current_user.role == "parent":
        p = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not p or not ParentStudent.query.filter_by(
            school_id=school_id, parent_id=p.id, student_id=payment.student_id
        ).first():
            return jsonify({"error": "Unauthorized access to receipt."}), 403
    elif current_user.role not in ("admin", "superadmin"):
        return jsonify({"error": "Unauthorized."}), 403

    school = db.session.get(School, payment.school_id)
    student = db.session.get(Student, payment.student_id)
    term = db.session.get(Term, payment.term_id)
    school_class = db.session.get(SchoolClass, student.class_id) if student and student.class_id else None

    return jsonify({
        "id": payment.id,
        "reference": payment.reference,
        "bank_reference": payment.bank_reference,
        "lipila_reference_id": payment.lipila_reference_id,
        "lipila_transaction_id": payment.lipila_transaction_id,
        "amount_paid": payment.amount_paid,
        "currency": payment.currency or "ZMW",
        "payment_method": payment.payment_method or "manual",
        "status": payment.status or "completed",
        "is_sandbox_simulated": bool(payment.is_sandbox_simulated),
        "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
        "school": _serialize_school(school),
        "student": {
            "id": student.id if student else None,
            "admission_no": student.admission_no if student else "—",
            "first_name": student.first_name if student else "—",
            "last_name": student.last_name if student else "",
            "class_name": school_class.name if school_class else "—",
        },
        "term_name": term.name if term else "—",
        "remaining_balance": calculate_balance(student.id, term.id, school_id) if (student and term) else 0.0,
    })


# ══════════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════

@api.route("/notifications", methods=["GET"])
@login_required
def api_notifications():
    if not current_user.school_id:
        return jsonify({"notifications": []})
    notes = (
        Notification.query.filter_by(school_id=current_user.school_id, user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({
        "notifications": [
            {
                "id": n.id,
                "message": n.message,
                "type": n.type,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ]
    })


@api.route("/notifications/<int:note_id>/read", methods=["POST"])
@login_required
def api_mark_notification_read(note_id):
    school_id = get_current_school_id()
    note = Notification.query.filter_by(id=note_id, school_id=school_id, user_id=current_user.id).first_or_404()
    note.is_read = True
    db.session.commit()
    return jsonify({"message": "Notification marked as read."})


# ══════════════════════════════════════════════════════════════════
#  SUPERADMIN CONSOLE — PLATFORM MONITORING, SCHOOL DETAILS & AUDIT
# ══════════════════════════════════════════════════════════════════

def _max_dt(*values):
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def _compute_school_last_activity(school: School) -> datetime.datetime | None:
    sid = school.id
    latest_log = (
        db.session.query(func.max(ActivityLog.created_at))
        .filter(ActivityLog.school_id == sid)
        .scalar()
    )
    latest_login = (
        db.session.query(func.max(User.last_login_at))
        .filter(User.school_id == sid)
        .scalar()
    )
    latest_sub = (
        db.session.query(func.max(Subscription.created_at))
        .filter(Subscription.school_id == sid)
        .scalar()
    )
    latest_sub_rec = (
        db.session.query(func.max(Subscription.reconciled_at))
        .filter(Subscription.school_id == sid)
        .scalar()
    )
    latest_pay = (
        db.session.query(func.max(Payment.payment_date))
        .filter(Payment.school_id == sid)
        .scalar()
    )
    latest_ann = (
        db.session.query(func.max(Announcement.created_at))
        .filter(Announcement.school_id == sid)
        .scalar()
    )
    latest_stu = (
        db.session.query(func.max(Student.created_at))
        .filter(Student.school_id == sid)
        .scalar()
    )
    latest_asgn = (
        db.session.query(func.max(Assignment.created_at))
        .filter(Assignment.school_id == sid)
        .scalar()
    )
    latest_subm = (
        db.session.query(func.max(Submission.submitted_at))
        .filter(Submission.school_id == sid)
        .scalar()
    )
    latest_mat = (
        db.session.query(func.max(Material.upload_date))
        .filter(Material.school_id == sid)
        .scalar()
    )
    latest_att_date = (
        db.session.query(func.max(Attendance.date))
        .filter(Attendance.school_id == sid)
        .scalar()
    )
    latest_att_dt = (
        datetime.datetime.combine(latest_att_date, datetime.time(12, 0))
        if latest_att_date
        else None
    )

    return _max_dt(
        school.last_activity_at,
        latest_log,
        latest_login,
        latest_sub,
        latest_sub_rec,
        latest_pay,
        latest_ann,
        latest_stu,
        latest_asgn,
        latest_subm,
        latest_mat,
        latest_att_dt,
        school.created_at,
    )


def _school_subscription_state(school: School) -> dict:
    now = utc_now()
    on_trial = school.is_on_trial()
    sub_active = school.subscription_active()

    has_past_due = (
        Subscription.query.filter_by(school_id=school.id, status="past_due").first()
        is not None
    )
    trial_expired = bool(
        school.plan == "free"
        and school.trial_ends_at
        and school.trial_ends_at <= now
        and (not school.subscription_ends_at or school.subscription_ends_at <= now)
    )
    paid_expired = bool(
        school.plan != "free"
        and not on_trial
        and (not school.subscription_ends_at or school.subscription_ends_at <= now)
    )
    is_expired_or_overdue = bool(has_past_due or trial_expired or paid_expired)

    if not school.is_active:
        status_label = "Suspended"
    elif is_expired_or_overdue:
        status_label = "Expired / Overdue"
    elif school.plan != "free" and sub_active:
        status_label = "Active Paid"
    elif on_trial:
        status_label = "On Trial"
    else:
        status_label = "Free Tier"

    return {
        "on_trial": on_trial,
        "subscription_active": sub_active,
        "is_expired_or_overdue": is_expired_or_overdue,
        "status_label": status_label,
    }


def _school_mrr_zmw(school: School) -> float:
    if not school.is_active or school.plan == "free":
        return 0.0
    if not school.subscription_active():
        return 0.0
    prices = current_app.config.get("PLAN_PRICES", {})
    info = prices.get(school.plan, {})
    if school.billing_cycle == "yearly":
        return round(float(info.get("amount_yearly", 0)) / 12.0, 2)
    return round(float(info.get("amount_monthly", 0)), 2)


def _serialize_school_for_superadmin(school: School) -> dict:
    sub_state = _school_subscription_state(school)
    last_activity = _compute_school_last_activity(school)
    admin_users = (
        User.query.filter_by(school_id=school.id, role="admin")
        .order_by(User.id.asc())
        .all()
    )
    primary_admin = admin_users[0] if admin_users else None

    return {
        **_serialize_school(school),
        **sub_state,
        "is_email_verified": bool(school.is_email_verified),
        "created_at": school.created_at.isoformat() if school.created_at else None,
        "last_activity_at": last_activity.isoformat() if last_activity else None,
        "suspended_at": school.suspended_at.isoformat() if school.suspended_at else None,
        "suspension_reason": school.suspension_reason,
        "mrr_zmw": _school_mrr_zmw(school),
        "student_count": Student.query.filter_by(school_id=school.id).count(),
        "teacher_count": Teacher.query.filter_by(school_id=school.id).count(),
        "parent_count": Parent.query.filter_by(school_id=school.id).count(),
        "admin_count": len(admin_users),
        "primary_admin": {
            "id": primary_admin.id,
            "username": primary_admin.username,
            "email": primary_admin.email or school.email,
            "is_verified": bool(primary_admin.is_verified),
            "last_login_at": (
                primary_admin.last_login_at.isoformat()
                if primary_admin.last_login_at
                else None
            ),
        }
        if primary_admin
        else None,
    }


def _build_activity_feed(
    *,
    school_id: int | None = None,
    category: str | None = None,
    role: str | None = None,
    status: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    search_q: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """
    Build a chronological activity timeline combining structured ActivityLog rows
    with genuine timestamped database records (without fabricating any events).
    """
    import json

    schools_q = School.query
    if school_id is not None:
        schools_q = schools_q.filter_by(id=school_id)
    school_map = {s.id: s for s in schools_q.all()}
    all_school_names = {s.id: s.name for s in School.query.all()}

    events: list[dict] = []
    seen_targets: set[tuple] = set()

    # 1. Structured audit log entries from activity_logs
    log_q = ActivityLog.query
    if school_id is not None:
        log_q = log_q.filter(ActivityLog.school_id == school_id)
    for log in log_q.order_by(ActivityLog.created_at.desc()).limit(500).all():
        if log.target_type and log.target_id:
            seen_targets.add((log.school_id, log.event_type, str(log.target_id)))
        meta = {}
        if log.metadata_json:
            try:
                meta = json.loads(log.metadata_json)
            except Exception:
                meta = {}
        events.append({
            "id": f"log-{log.id}",
            "source": "audit_log",
            "timestamp": log.created_at.isoformat() if log.created_at else None,
            "_dt": log.created_at or datetime.datetime.min,
            "school_id": log.school_id,
            "school_name": all_school_names.get(log.school_id, "Platform System") if log.school_id else "Platform System",
            "category": log.category,
            "event_type": log.event_type,
            "status": log.status or "success",
            "actor_username": log.actor_username or "system",
            "actor_role": log.actor_role or "system",
            "description": log.description,
            "metadata": meta,
        })

    # 2. Genuine timestamped database records (for events recorded in primary tables)
    for sid, s_obj in school_map.items():
        if s_obj.created_at and (sid, "school_registered", str(sid)) not in seen_targets:
            events.append({
                "id": f"school-reg-{sid}",
                "source": "db_record",
                "timestamp": s_obj.created_at.isoformat(),
                "_dt": s_obj.created_at,
                "school_id": sid,
                "school_name": s_obj.name,
                "category": "onboarding",
                "event_type": "school_registered",
                "status": "success",
                "actor_username": "admin",
                "actor_role": "admin",
                "description": f"School '{s_obj.name}' (/s/{s_obj.subdomain}) registered on the platform.",
                "metadata": {"subdomain": s_obj.subdomain, "plan": s_obj.plan},
            })

        if not s_obj.is_active and s_obj.suspended_at and (sid, "school_suspended", str(sid)) not in seen_targets:
            events.append({
                "id": f"school-susp-{sid}",
                "source": "db_record",
                "timestamp": s_obj.suspended_at.isoformat(),
                "_dt": s_obj.suspended_at,
                "school_id": sid,
                "school_name": s_obj.name,
                "category": "school_status",
                "event_type": "school_suspended",
                "status": "warning",
                "actor_username": "superadmin",
                "actor_role": "superadmin",
                "description": f"School '{s_obj.name}' suspended. Reason: {s_obj.suspension_reason or 'Not specified'}",
                "metadata": {"reason": s_obj.suspension_reason},
            })

        # Subscriptions with timestamps
        for sub in Subscription.query.filter_by(school_id=sid).order_by(Subscription.created_at.desc()).limit(100).all():
            ref = sub.lipila_reference_id or sub.stripe_subscription_id or f"SUB-{sub.id}"
            ev_type = (
                "subscription_confirmed"
                if sub.status in ("active", "completed")
                else "subscription_failed"
                if sub.status in ("failed", "past_due", "canceled")
                else "subscription_initiated"
            )
            ev_status = (
                "success"
                if sub.status in ("active", "completed")
                else "failed"
                if sub.status in ("failed", "past_due", "canceled")
                else "pending"
            )
            dt_val = sub.reconciled_at or sub.created_at
            if dt_val and (sid, ev_type, str(ref)) not in seen_targets:
                events.append({
                    "id": f"sub-{sub.id}",
                    "source": "db_record",
                    "timestamp": dt_val.isoformat(),
                    "_dt": dt_val,
                    "school_id": sid,
                    "school_name": s_obj.name,
                    "category": "subscription",
                    "event_type": ev_type,
                    "status": ev_status,
                    "actor_username": "admin",
                    "actor_role": "admin",
                    "description": (
                        f"Subscription ({(sub.plan or 'plan').title()}, {sub.billing_cycle or 'monthly'}) — "
                        f"K{float(sub.amount or 0):.2f} [{sub.status}] (Ref: {ref})."
                    ),
                    "metadata": {"reference": ref, "plan": sub.plan, "amount": sub.amount, "status": sub.status},
                })

        # Fee payments (redacted to receipt/reference + ZMW amount)
        for pay in Payment.query.filter_by(school_id=sid).order_by(Payment.payment_date.desc()).limit(100).all():
            ref = pay.reference or pay.lipila_reference_id or f"PAY-{pay.id}"
            ev_type = "fee_payment_confirmed" if pay.status in ("completed", None) else f"fee_payment_{pay.status}"
            ev_status = "success" if pay.status in ("completed", None) else ("failed" if pay.status == "failed" else "pending")
            if pay.payment_date and (sid, ev_type, str(ref)) not in seen_targets:
                events.append({
                    "id": f"pay-{pay.id}",
                    "source": "db_record",
                    "timestamp": pay.payment_date.isoformat(),
                    "_dt": pay.payment_date,
                    "school_id": sid,
                    "school_name": s_obj.name,
                    "category": "payment",
                    "event_type": ev_type,
                    "status": ev_status,
                    "actor_username": pay.payment_method or "school_billing",
                    "actor_role": "parent",
                    "description": f"School fee transaction ({pay.payment_method or 'manual'}) — K{float(pay.amount_paid or 0):.2f} (Ref: {ref}).",
                    "metadata": {"reference": ref, "amount": pay.amount_paid, "status": pay.status or "completed"},
                })

        # Student account creation (redacted to admission_no)
        for stu in Student.query.filter_by(school_id=sid).order_by(Student.created_at.desc()).limit(80).all():
            if stu.created_at and (sid, "student_created", str(stu.admission_no)) not in seen_targets:
                events.append({
                    "id": f"stu-{stu.id}",
                    "source": "db_record",
                    "timestamp": stu.created_at.isoformat(),
                    "_dt": stu.created_at,
                    "school_id": sid,
                    "school_name": s_obj.name,
                    "category": "student",
                    "event_type": "student_created",
                    "status": "success",
                    "actor_username": "admin",
                    "actor_role": "admin",
                    "description": f"Student enrolled with admission number '{stu.admission_no}'.",
                    "metadata": {"admission_no": stu.admission_no},
                })

        # Staff / user account creation
        for u in User.query.filter(User.school_id == sid, User.role.in_(["admin", "teacher", "parent"])).order_by(User.created_at.desc()).limit(60).all():
            ev_type = "teacher_created" if u.role == "teacher" else f"{u.role}_account_created"
            if u.created_at and (sid, ev_type, str(u.username)) not in seen_targets:
                events.append({
                    "id": f"user-{u.id}",
                    "source": "db_record",
                    "timestamp": u.created_at.isoformat(),
                    "_dt": u.created_at,
                    "school_id": sid,
                    "school_name": s_obj.name,
                    "category": "staff" if u.role in ("admin", "teacher") else "auth",
                    "event_type": ev_type,
                    "status": "success",
                    "actor_username": u.username,
                    "actor_role": u.role,
                    "description": f"{u.role.title()} account '{u.username}' provisioned.",
                    "metadata": {"username": u.username, "role": u.role},
                })

        # Announcements
        for ann in Announcement.query.filter_by(school_id=sid).order_by(Announcement.created_at.desc()).limit(50).all():
            if ann.created_at and (sid, "announcement_published", str(ann.title)) not in seen_targets:
                events.append({
                    "id": f"ann-{ann.id}",
                    "source": "db_record",
                    "timestamp": ann.created_at.isoformat(),
                    "_dt": ann.created_at,
                    "school_id": sid,
                    "school_name": s_obj.name,
                    "category": "announcement",
                    "event_type": "announcement_published",
                    "status": "success",
                    "actor_username": "admin",
                    "actor_role": "admin",
                    "description": f"Announcement published: '{ann.title}'.",
                    "metadata": {"title": ann.title},
                })

        # Assignments
        for asgn in Assignment.query.filter_by(school_id=sid).order_by(Assignment.created_at.desc()).limit(50).all():
            if asgn.created_at and (sid, "assignment_created", str(asgn.title)) not in seen_targets:
                events.append({
                    "id": f"asgn-{asgn.id}",
                    "source": "db_record",
                    "timestamp": asgn.created_at.isoformat(),
                    "_dt": asgn.created_at,
                    "school_id": sid,
                    "school_name": s_obj.name,
                    "category": "academic",
                    "event_type": "assignment_created",
                    "status": "success",
                    "actor_username": "teacher",
                    "actor_role": "teacher",
                    "description": f"Assignment published: '{asgn.title}'.",
                    "metadata": {"title": asgn.title},
                })

        # Aggregated daily Attendance per (class_id, date)
        att_groups = (
            db.session.query(
                Attendance.class_id,
                Attendance.date,
                func.count(Attendance.id),
            )
            .filter(Attendance.school_id == sid)
            .group_by(Attendance.class_id, Attendance.date)
            .order_by(Attendance.date.desc())
            .limit(40)
            .all()
        )
        cls_names = {c.id: c.name for c in SchoolClass.query.filter_by(school_id=sid).all()}
        for cid, att_date, cnt in att_groups:
            if not att_date:
                continue
            cname = cls_names.get(cid, f"Class {cid}")
            if (sid, "attendance_recorded", cname) in seen_targets:
                continue
            att_dt = datetime.datetime.combine(att_date, datetime.time(12, 0))
            events.append({
                "id": f"att-{sid}-{cid}-{att_date.isoformat()}",
                "source": "db_record",
                "timestamp": att_dt.isoformat(),
                "_dt": att_dt,
                "school_id": sid,
                "school_name": s_obj.name,
                "category": "attendance",
                "event_type": "attendance_recorded",
                "status": "success",
                "actor_username": "teacher",
                "actor_role": "teacher",
                "description": f"Attendance recorded for {cname} ({att_date.isoformat()}) — {cnt} student record(s).",
                "metadata": {"class_name": cname, "date": att_date.isoformat(), "count": cnt},
            })

    # Apply server-side filters
    filtered = []
    q_lower = (search_q or "").strip().lower()
    cat_filter = (category or "").strip().lower()
    role_filter = (role or "").strip().lower()
    status_filter = (status or "").strip().lower()

    for ev in events:
        if cat_filter and cat_filter != "all" and ev["category"].lower() != cat_filter:
            continue
        if role_filter and role_filter != "all" and (ev["actor_role"] or "").lower() != role_filter:
            continue
        if status_filter and status_filter != "all" and (ev["status"] or "").lower() != status_filter:
            continue
        ev_date = ev["_dt"].date() if ev.get("_dt") else None
        if date_from and (not ev_date or ev_date < date_from):
            continue
        if date_to and (not ev_date or ev_date > date_to):
            continue
        if q_lower:
            haystack = " ".join([
                str(ev.get("description") or ""),
                str(ev.get("event_type") or ""),
                str(ev.get("actor_username") or ""),
                str(ev.get("school_name") or ""),
                str(ev.get("category") or ""),
            ]).lower()
            if q_lower not in haystack:
                continue
        filtered.append(ev)

    filtered.sort(key=lambda x: x["_dt"], reverse=True)

    total = len(filtered)
    safe_per_page = max(1, min(int(per_page or 25), 100))
    total_pages = max(1, (total + safe_per_page - 1) // safe_per_page)
    safe_page = max(1, min(int(page or 1), total_pages))
    start_idx = (safe_page - 1) * safe_per_page
    page_items = []
    for item in filtered[start_idx : start_idx + safe_per_page]:
        clean_item = {k: v for k, v in item.items() if k != "_dt"}
        page_items.append(clean_item)

    audit_log_count = ActivityLog.query.filter_by(school_id=school_id).count() if school_id else ActivityLog.query.count()

    return {
        "items": page_items,
        "total": total,
        "page": safe_page,
        "per_page": safe_per_page,
        "total_pages": total_pages,
        "structured_audit_log_count": audit_log_count,
        "audit_logging_notice": (
            "Structured audit logging (activity_logs) records all logins, school status changes, "
            "subscriptions, payments, and academic updates in real time. Earlier events are surfaced "
            "only where genuine database timestamps exist; unrecorded historical actions are not fabricated."
        ),
    }


@api.route("/superadmin/overview", methods=["GET"])
@login_required
def api_superadmin_overview():
    err = _require_role("superadmin")
    if err:
        return err

    now = utc_now()
    cutoff_24h = now - datetime.timedelta(hours=24)
    cutoff_7d = now - datetime.timedelta(days=7)

    schools = School.query.order_by(School.created_at.desc()).all()
    serialized_schools = [_serialize_school_for_superadmin(s) for s in schools]

    total_students = Student.query.count()
    total_teachers = Teacher.query.count()
    total_admins = User.query.filter_by(role="admin").count()
    total_parents = Parent.query.count()

    # Platform Subscription Revenue (strictly SaaS subscriptions, NOT tenant school fee collections)
    subscription_revenue_zmw = (
        db.session.query(func.coalesce(func.sum(Subscription.amount), 0.0))
        .filter(Subscription.status.in_(["active", "completed"]))
        .scalar()
        or 0.0
    )
    completed_subs_count = Subscription.query.filter(
        Subscription.status.in_(["active", "completed"])
    ).count()

    pending_subs_zmw = (
        db.session.query(func.coalesce(func.sum(Subscription.amount), 0.0))
        .filter(Subscription.status == "pending")
        .scalar()
        or 0.0
    )
    pending_subs_count = Subscription.query.filter_by(status="pending").count()

    failed_subs_zmw = (
        db.session.query(func.coalesce(func.sum(Subscription.amount), 0.0))
        .filter(Subscription.status.in_(["failed", "past_due", "canceled"]))
        .scalar()
        or 0.0
    )
    failed_subs_count = Subscription.query.filter(
        Subscription.status.in_(["failed", "past_due", "canceled"])
    ).count()

    # Separate tenant school fee collections (explicitly NOT counted as platform revenue)
    school_fee_collections_zmw = (
        db.session.query(func.coalesce(func.sum(Payment.amount_paid), 0.0))
        .filter(db.or_(Payment.status == "completed", Payment.status.is_(None)))
        .scalar()
        or 0.0
    )

    active_24h = 0
    active_7d = 0
    for s_data in serialized_schools:
        if s_data.get("last_activity_at"):
            try:
                dt = datetime.datetime.fromisoformat(s_data["last_activity_at"])
                if dt >= cutoff_24h:
                    active_24h += 1
                if dt >= cutoff_7d:
                    active_7d += 1
            except ValueError:
                pass

    estimated_mrr_zmw = round(sum(s["mrr_zmw"] for s in serialized_schools), 2)

    plan_distribution = {"free": 0, "starter": 0, "growth": 0, "enterprise": 0}
    for s in schools:
        plan_key = (s.plan or "free").lower()
        plan_distribution[plan_key] = plan_distribution.get(plan_key, 0) + 1

    school_name_map = {s.id: s.name for s in schools}
    recent_subs = (
        Subscription.query.order_by(Subscription.created_at.desc())
        .limit(12)
        .all()
    )

    recent_activity_feed = _build_activity_feed(page=1, per_page=15)

    return jsonify({
        "metrics": {
            "total_schools": len(schools),
            "active_schools": sum(1 for s in schools if s.is_active),
            "suspended_schools": sum(1 for s in schools if not s.is_active),
            "trial_schools": sum(1 for s in serialized_schools if s["on_trial"]),
            "expired_or_overdue_schools": sum(
                1 for s in serialized_schools if s["is_expired_or_overdue"]
            ),
            "paid_schools": sum(
                1 for s in schools if s.plan in ("starter", "growth", "enterprise")
            ),
            "free_schools": sum(1 for s in schools if (s.plan or "free") == "free"),
            "active_schools_24h": active_24h,
            "active_schools_7d": active_7d,
            "total_students": total_students,
            "total_teachers": total_teachers,
            "total_admins": total_admins,
            "total_parents": total_parents,
            "total_staff_and_admins": total_teachers + total_admins,
            # Platform Subscription Revenue (kept backward-compatible as total_revenue_zmw as well)
            "total_revenue_zmw": round(float(subscription_revenue_zmw), 2),
            "subscription_revenue_zmw": round(float(subscription_revenue_zmw), 2),
            "estimated_mrr_zmw": estimated_mrr_zmw,
            "completed_subscriptions_count": completed_subs_count,
            "pending_subscriptions_count": pending_subs_count,
            "pending_subscriptions_zmw": round(float(pending_subs_zmw), 2),
            "failed_subscriptions_count": failed_subs_count,
            "failed_subscriptions_zmw": round(float(failed_subs_zmw), 2),
            # Tenant fee volume (explicitly separated from platform revenue)
            "school_fee_collections_zmw": round(float(school_fee_collections_zmw), 2),
            "plan_distribution": plan_distribution,
        },
        "schools": serialized_schools,
        "recent_subscriptions": [
            {
                "id": sub.id,
                "school_id": sub.school_id,
                "school_name": school_name_map.get(sub.school_id, f"School #{sub.school_id}"),
                "plan": sub.plan,
                "billing_cycle": sub.billing_cycle,
                "amount": sub.amount,
                "currency": sub.currency or "ZMW",
                "status": sub.status,
                "payment_method": sub.payment_method,
                "lipila_reference_id": sub.lipila_reference_id,
                "lipila_transaction_id": sub.lipila_transaction_id,
                "is_sandbox_simulated": bool(sub.is_sandbox_simulated),
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
                "reconciled_at": sub.reconciled_at.isoformat() if sub.reconciled_at else None,
            }
            for sub in recent_subs
        ],
        "recent_activity": recent_activity_feed["items"],
        "audit_logging_notice": recent_activity_feed["audit_logging_notice"],
    })


@api.route("/superadmin/schools/<int:school_id>", methods=["GET"])
@login_required
def api_superadmin_school_detail(school_id):
    err = _require_role("superadmin")
    if err:
        return err

    school = db.session.get(School, school_id)
    if not school:
        return jsonify({"error": "School not found."}), 404

    school_summary = _serialize_school_for_superadmin(school)

    # A. School Administrators
    admins = (
        User.query.filter_by(school_id=school.id, role="admin")
        .order_by(User.id.asc())
        .all()
    )
    administrators = [
        {
            "id": a.id,
            "username": a.username,
            "email": a.email or school.email,
            "is_verified": bool(a.is_verified),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
        }
        for a in admins
    ]

    # B. School Usage Statistics (aggregated / privacy-preserving)
    students_count = Student.query.filter_by(school_id=school.id).count()
    teachers_count = Teacher.query.filter_by(school_id=school.id).count()
    parents_count = Parent.query.filter_by(school_id=school.id).count()
    admins_count = len(admins)
    classes = SchoolClass.query.filter_by(school_id=school.id).order_by(SchoolClass.name.asc()).all()
    subjects = Subject.query.filter_by(school_id=school.id).order_by(Subject.name.asc()).all()
    terms = Term.query.filter_by(school_id=school.id).order_by(Term.start_date.desc()).all()
    active_term = next((t for t in terms if t.is_active), terms[0] if terms else None)

    attendance_total = Attendance.query.filter_by(school_id=school.id).count()
    attendance_present = Attendance.query.filter_by(school_id=school.id, status="Present").count()
    attendance_absent = Attendance.query.filter_by(school_id=school.id, status="Absent").count()
    latest_att_date = (
        db.session.query(func.max(Attendance.date))
        .filter(Attendance.school_id == school.id)
        .scalar()
    )

    exams_count = Exam.query.filter_by(school_id=school.id).count()
    results_count = Result.query.filter_by(school_id=school.id).count()
    assignments_count = Assignment.query.filter_by(school_id=school.id).count()
    submissions_count = Submission.query.filter_by(school_id=school.id).count()
    materials_count = Material.query.filter_by(school_id=school.id).count()
    announcements_count = Announcement.query.filter_by(school_id=school.id).count()
    notifications_count = Notification.query.filter_by(school_id=school.id).count()

    # Tenant school fee stats (explicitly separated from platform subscription revenue)
    fee_completed_zmw = (
        db.session.query(func.coalesce(func.sum(Payment.amount_paid), 0.0))
        .filter(
            Payment.school_id == school.id,
            db.or_(Payment.status == "completed", Payment.status.is_(None)),
        )
        .scalar()
        or 0.0
    )
    fee_completed_count = Payment.query.filter(
        Payment.school_id == school.id,
        db.or_(Payment.status == "completed", Payment.status.is_(None)),
    ).count()

    teacher_map = {
        t.id: f"{t.first_name} {t.last_name} ({t.staff_no})"
        for t in Teacher.query.filter_by(school_id=school.id).all()
    }
    classes_summary = [
        {
            "id": c.id,
            "name": c.name,
            "capacity": c.capacity,
            "student_count": Student.query.filter_by(school_id=school.id, class_id=c.id).count(),
            "class_teacher": teacher_map.get(c.class_teacher_id, "Unassigned"),
        }
        for c in classes
    ]

    terms_summary = [
        {
            "id": t.id,
            "name": t.name,
            "start_date": t.start_date.isoformat() if t.start_date else None,
            "end_date": t.end_date.isoformat() if t.end_date else None,
            "is_active": bool(t.is_active),
            "exams_count": Exam.query.filter_by(school_id=school.id, term_id=t.id).count(),
        }
        for t in terms
    ]

    recent_announcements = [
        {
            "id": a.id,
            "title": a.title,
            "priority": a.priority or "Normal",
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in Announcement.query.filter_by(school_id=school.id)
        .order_by(Announcement.created_at.desc())
        .limit(8)
        .all()
    ]

    # C. Subscription & Payments History
    subs = (
        Subscription.query.filter_by(school_id=school.id)
        .order_by(Subscription.created_at.desc())
        .all()
    )
    plan_limits_cfg = current_app.config.get("PLAN_LIMITS", {})
    current_limits = plan_limits_cfg.get(school.plan, plan_limits_cfg.get("free", {"students": 50, "teachers": 5}))

    paid_sub_zmw = sum(float(s.amount or 0) for s in subs if s.status in ("active", "completed"))
    pending_sub_zmw = sum(float(s.amount or 0) for s in subs if s.status == "pending")
    failed_sub_zmw = sum(float(s.amount or 0) for s in subs if s.status in ("failed", "past_due", "canceled"))

    verified_paid_plans = sorted({
        s.plan for s in subs if s.status in ("active", "completed") and s.plan
    })

    # D. School Activity Timeline (with optional query filters)
    category = request.args.get("category")
    role = request.args.get("role")
    status = request.args.get("status")
    q = request.args.get("q")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    date_from = None
    date_to = None
    if request.args.get("date_from"):
        try:
            date_from = datetime.datetime.strptime(request.args["date_from"], "%Y-%m-%d").date()
        except ValueError:
            pass
    if request.args.get("date_to"):
        try:
            date_to = datetime.datetime.strptime(request.args["date_to"], "%Y-%m-%d").date()
        except ValueError:
            pass

    timeline = _build_activity_feed(
        school_id=school.id,
        category=category,
        role=role,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search_q=q,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "school": school_summary,
        "administrators": administrators,
        "usage": {
            "students_count": students_count,
            "teachers_count": teachers_count,
            "parents_count": parents_count,
            "admins_count": admins_count,
            "classes_count": len(classes),
            "subjects_count": len(subjects),
            "terms_count": len(terms),
            "active_term_name": active_term.name if active_term else "None",
            "attendance_records_count": attendance_total,
            "attendance_present_count": attendance_present,
            "attendance_absent_count": attendance_absent,
            "latest_attendance_date": latest_att_date.isoformat() if latest_att_date else None,
            "exams_count": exams_count,
            "results_count": results_count,
            "assignments_count": assignments_count,
            "submissions_count": submissions_count,
            "materials_count": materials_count,
            "announcements_count": announcements_count,
            "notifications_count": notifications_count,
            "tenant_fee_payments_count": fee_completed_count,
            "tenant_fee_collections_zmw": round(float(fee_completed_zmw), 2),
            "plan_limits": current_limits,
            "classes_summary": classes_summary,
            "terms_summary": terms_summary,
            "recent_announcements": recent_announcements,
        },
        "billing": {
            "current_plan": school.plan,
            "billing_cycle": school.billing_cycle,
            "subscription_status_label": school_summary["status_label"],
            "on_trial": school_summary["on_trial"],
            "subscription_active": school_summary["subscription_active"],
            "is_expired_or_overdue": school_summary["is_expired_or_overdue"],
            "trial_ends_at": school_summary["trial_ends_at"],
            "subscription_ends_at": school_summary["subscription_ends_at"],
            "mrr_zmw": school_summary["mrr_zmw"],
            "verified_paid_plans": verified_paid_plans,
            "totals": {
                "paid_zmw": round(paid_sub_zmw, 2),
                "pending_zmw": round(pending_sub_zmw, 2),
                "failed_zmw": round(failed_sub_zmw, 2),
                "completed_count": sum(1 for s in subs if s.status in ("active", "completed")),
                "pending_count": sum(1 for s in subs if s.status == "pending"),
                "failed_count": sum(1 for s in subs if s.status in ("failed", "past_due", "canceled")),
            },
            "subscriptions": [
                {
                    "id": s.id,
                    "plan": s.plan,
                    "billing_cycle": s.billing_cycle,
                    "amount": s.amount,
                    "currency": s.currency or "ZMW",
                    "status": s.status,
                    "payment_method": s.payment_method,
                    "account_number": s.account_number,
                    "lipila_reference_id": s.lipila_reference_id,
                    "lipila_transaction_id": s.lipila_transaction_id,
                    "stripe_subscription_id": s.stripe_subscription_id,
                    "is_sandbox_simulated": bool(s.is_sandbox_simulated),
                    "period_start": s.period_start.isoformat() if s.period_start else None,
                    "period_end": s.period_end.isoformat() if s.period_end else None,
                    "reconciled_at": s.reconciled_at.isoformat() if s.reconciled_at else None,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in subs
            ],
        },
        "activity": timeline,
    })


@api.route("/superadmin/activity", methods=["GET"])
@login_required
def api_superadmin_activity():
    err = _require_role("superadmin")
    if err:
        return err

    school_id = request.args.get("school_id", type=int)
    category = request.args.get("category")
    role = request.args.get("role")
    status = request.args.get("status")
    q = request.args.get("q")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    date_from = None
    date_to = None
    if request.args.get("date_from"):
        try:
            date_from = datetime.datetime.strptime(request.args["date_from"], "%Y-%m-%d").date()
        except ValueError:
            pass
    if request.args.get("date_to"):
        try:
            date_to = datetime.datetime.strptime(request.args["date_to"], "%Y-%m-%d").date()
        except ValueError:
            pass

    feed = _build_activity_feed(
        school_id=school_id,
        category=category,
        role=role,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search_q=q,
        page=page,
        per_page=per_page,
    )
    return jsonify(feed)


@api.route("/superadmin/schools/<int:school_id>/status", methods=["POST"])
@api.route("/superadmin/schools/<int:school_id>/toggle", methods=["POST"])
@login_required
def api_superadmin_toggle_school(school_id):
    err = _require_role("superadmin")
    if err:
        return err

    school = db.session.get(School, school_id)
    if not school:
        return jsonify({"error": "School not found."}), 404

    data = request.get_json(silent=True) or request.form or {}
    requested_action = (data.get("action") or "").strip().lower()
    reason = (data.get("reason") or "").strip()

    if requested_action == "suspend":
        new_active = False
    elif requested_action in ("activate", "reactivate"):
        new_active = True
    else:
        new_active = not school.is_active

    if not new_active and not reason:
        reason = "Administrative suspension by platform superadmin"
    elif new_active and not reason:
        reason = "Account reactivated by platform superadmin"

    now = utc_now()
    school.is_active = new_active
    if not new_active:
        school.suspended_at = now
        school.suspension_reason = reason
    else:
        school.suspended_at = None
        school.suspension_reason = None

    action_word = "reactivated" if new_active else "suspended"
    record_activity(
        "school_status",
        "school_reactivated" if new_active else "school_suspended",
        f"School '{school.name}' (/s/{school.subdomain}) {action_word} by '{current_user.username}'. Reason: {reason}",
        school_id=school.id,
        actor_user=current_user,
        status="success" if new_active else "warning",
        target_type="school",
        target_id=school.id,
        metadata={"action": action_word, "reason": reason},
        commit=False,
    )
    db.session.commit()

    return jsonify({
        "message": f"School '{school.name}' has been {action_word}.",
        "school": _serialize_school_for_superadmin(school),
    })


@api.route("/superadmin/schools/<int:school_id>/plan", methods=["POST"])
@login_required
def api_superadmin_override_plan(school_id):
    err = _require_role("superadmin")
    if err:
        return err

    school = db.session.get(School, school_id)
    if not school:
        return jsonify({"error": "School not found."}), 404

    data = request.get_json(silent=True) or request.form or {}
    new_plan = (data.get("plan") or "").strip().lower()
    reason = (data.get("reason") or "Administrative plan adjustment").strip()

    if new_plan not in ("free", "starter", "growth", "enterprise"):
        return jsonify({"error": "Invalid plan selected."}), 400

    old_plan = school.plan or "free"
    if new_plan == old_plan:
        return jsonify({
            "message": f"School '{school.name}' is already on the {new_plan.title()} plan.",
            "school": _serialize_school_for_superadmin(school),
        })

    # Payment integrity guard: Superadmin cannot bypass billing or falsely mark a paid plan active
    # unless the school has a verified active/completed Subscription record for that paid plan.
    if new_plan in ("starter", "growth", "enterprise"):
        verified_sub = (
            Subscription.query.filter(
                Subscription.school_id == school.id,
                Subscription.plan == new_plan,
                Subscription.status.in_(["active", "completed"]),
            )
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not verified_sub:
            record_activity(
                "subscription",
                "plan_change_blocked_unpaid",
                f"Blocked unpaid plan upgrade to '{new_plan.title()}' for '{school.name}' (no verified Lipila subscription payment).",
                school_id=school.id,
                actor_user=current_user,
                status="failed",
                target_type="school",
                target_id=school.id,
                metadata={"requested_plan": new_plan, "old_plan": old_plan, "reason": reason},
                commit=True,
            )
            return jsonify({
                "error": (
                    f"Cannot assign paid plan '{new_plan.title()}' without a verified subscription payment. "
                    "Schools must complete checkout via Lipila Billing, or you may sync a plan that has a verified payment."
                )
            }), 400

        school.plan = new_plan
        school.billing_cycle = verified_sub.billing_cycle or school.billing_cycle
        if verified_sub.period_end:
            school.subscription_ends_at = verified_sub.period_end
    else:
        # Downgrading to 'free' tier is permitted (e.g., after expiry/cancellation)
        school.plan = "free"

    record_activity(
        "subscription",
        "subscription_plan_changed",
        f"School '{school.name}' plan changed from {old_plan.title()} to {new_plan.title()} by '{current_user.username}'. Reason: {reason}",
        school_id=school.id,
        actor_user=current_user,
        status="info",
        target_type="school",
        target_id=school.id,
        metadata={"old_plan": old_plan, "new_plan": new_plan, "reason": reason},
        commit=False,
    )
    db.session.commit()

    return jsonify({
        "message": f"School '{school.name}' plan updated to {new_plan.title()}.",
        "school": _serialize_school_for_superadmin(school),
    })
