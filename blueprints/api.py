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
    AcademicYear,
    Term,
    Exam,
    Result,
    FeeStructure,
    Payment,
    Attendance,
    SubjectAttendance,
    Timetable,
    Announcement,
    Notification,
    Material,
    Assignment,
    Submission,
    ActivityLog,
    ClassTeacherAllocation,
    SubstituteAllocation,
    SMSSettings,
    SMSMessage,
    SMSDeliveryEvent,
    ParentCommunicationLog,
    AbsenteeismIntervention,
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
    find_user_for_login,
    handle_superadmin_recovery,
)
from services.lipila import LipilaClient, LipilaError, normalize_zambia_phone
from services.sms_service import send_school_sms, normalize_phone_number, SMSToClient
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

    target_school = getattr(g, "school", None)
    if school_subdomain:
        target_school = School.query.filter_by(
            subdomain=school_subdomain
        ).first()

    user = find_user_for_login(
        identifier=username,
        school_subdomain=school_subdomain,
        target_school=target_school,
    )

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


@api.route("/auth/superadmin/recover", methods=["POST"])
def api_superadmin_recover():
    data = request.get_json(silent=True) or (request.form.to_dict() if request.form else {})
    header_token = request.headers.get("X-Recovery-Token")
    result, code = handle_superadmin_recovery(data=data, header_token=header_token)
    return jsonify(result), code


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
    pending_results_count = sum(1 for r in all_results if getattr(r, "status", None) == "submitted")

    attendance_all = Attendance.query.filter_by(school_id=school_id).all()
    present_count = sum(1 for a in attendance_all if a.status in ("Present", "Late"))
    absent_count = sum(1 for a in attendance_all if a.status in ("Absent", "Sick", "Excused"))

    # Today's attendance analytics & absent students list
    today_date = datetime.date.today()
    today_attendance = Attendance.query.filter_by(school_id=school_id, date=today_date).all()
    today_present = sum(1 for a in today_attendance if a.status in ("Present", "Late"))
    today_absent = sum(1 for a in today_attendance if a.status in ("Absent", "Sick", "Excused"))
    today_marked = len(today_attendance)
    today_rate = round((today_present / today_marked) * 100, 1) if today_marked > 0 else 0.0

    active_term = terms[0] if terms else None
    class_map = {c.id: c.name for c in classes}
    term_map = {t.id: t.name for t in terms}
    subj_map = {s.id: s.name for s in subjects}
    teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
    student_map = {s.id: f"{s.first_name} {s.last_name} ({s.admission_no})" for s in students}
    parent_map = {p.id: p.phone for p in Parent.query.filter_by(school_id=school_id).all()}
    student_lookup = {s.id: s for s in students}

    absent_today_students = []
    for a in today_attendance:
        if a.status in ("Absent", "Sick", "Excused"):
            s_obj = student_lookup.get(a.student_id)
            if s_obj:
                absent_today_students.append({
                    "id": s_obj.id,
                    "admission_no": s_obj.admission_no,
                    "name": f"{s_obj.first_name} {s_obj.last_name}",
                    "class_name": class_map.get(s_obj.class_id, "—"),
                    "status": a.status,
                    "remarks": getattr(a, "remarks", "") or "",
                    "guardian_phone": parent_map.get(s_obj.parent_id, "No contact on file"),
                })

    # Outstanding fee balances for current active term
    total_outstanding_zmw = 0.0
    if active_term:
        for s in students:
            bal = calculate_balance(s.id, active_term.id, school_id)
            if bal > 0:
                total_outstanding_zmw += bal
    total_outstanding_zmw = round(total_outstanding_zmw, 2)

    current_school_rec = db.session.get(School, school_id)
    school_profile = {
        "id": current_school_rec.id,
        "name": current_school_rec.name,
        "subdomain": current_school_rec.subdomain,
        "email": current_school_rec.email,
        "phone": current_school_rec.phone or "",
        "address": current_school_rec.address or "",
        "logo_url": current_school_rec.logo_url or "",
        "currency": getattr(current_school_rec, "currency", "ZMW") or "ZMW",
        "plan": current_school_rec.plan,
    }

    return jsonify({
        "metrics": {
            "total_students": len(students),
            "total_teachers": len(teachers),
            "total_parents": Parent.query.filter_by(school_id=school_id).count(),
            "total_classes": len(classes),
            "total_subjects": len(subjects),
            "total_collected_zmw": round(float(total_collected), 2),
            "total_outstanding_zmw": total_outstanding_zmw,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "present_count": present_count,
            "absent_count": absent_count,
            "today_present": today_present,
            "today_absent": today_absent,
            "today_marked": today_marked,
            "today_rate": today_rate,
            "pending_results_count": pending_results_count,
        },
        "absent_today": absent_today_students,
        "school": school_profile,
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

    today_date = datetime.date.today()
    assigned_class_info = None

    if teacher_rec:
        active_alloc = ClassTeacherAllocation.query.filter_by(
            school_id=school_id, teacher_id=teacher_rec.id, status="active"
        ).first()

        assigned_class_obj = None
        is_substitute = False
        sub_reason = None

        if active_alloc:
            assigned_class_obj = db.session.get(SchoolClass, active_alloc.class_id)

        if not assigned_class_obj:
            assigned_class_obj = SchoolClass.query.filter_by(
                school_id=school_id, class_teacher_id=teacher_rec.id, is_active=True
            ).first()

        sub_alloc = SubstituteAllocation.query.filter(
            SubstituteAllocation.school_id == school_id,
            SubstituteAllocation.substitute_teacher_id == teacher_rec.id,
            SubstituteAllocation.is_active.is_(True),
            SubstituteAllocation.start_date <= today_date,
            SubstituteAllocation.end_date >= today_date,
        ).first()

        if sub_alloc and not assigned_class_obj:
            assigned_class_obj = db.session.get(SchoolClass, sub_alloc.class_id)
            is_substitute = True
            sub_reason = sub_alloc.reason

        if assigned_class_obj:
            c_students = Student.query.filter_by(
                school_id=school_id, class_id=assigned_class_obj.id, status="active"
            ).all()
            total_students_c = len(c_students)
            boys_count = sum(1 for s in c_students if (s.gender or "").lower() == "male")
            girls_count = sum(1 for s in c_students if (s.gender or "").lower() == "female")

            today_att = Attendance.query.filter_by(
                school_id=school_id, class_id=assigned_class_obj.id, date=today_date
            ).all()
            att_marked = len(today_att) > 0
            att_status = "submitted" if att_marked else "not_started"
            first_att = today_att[0] if att_marked else None
            submitted_at = first_att.updated_at.isoformat() if (first_att and first_att.updated_at) else None

            pres_c = sum(1 for a in today_att if a.status in ("Present", "Late"))
            abs_c = sum(1 for a in today_att if a.status in ("Absent", "Sick"))
            late_c = sum(1 for a in today_att if a.status == "Late")
            exc_c = sum(1 for a in today_att if a.status == "Excused")

            c_timetables = Timetable.query.filter_by(
                school_id=school_id, class_id=assigned_class_obj.id, is_active=True
            ).order_by(Timetable.start_time.asc()).all()

            assigned_class_info = {
                "id": assigned_class_obj.id,
                "name": assigned_class_obj.name,
                "grade_level": getattr(assigned_class_obj, "grade_level", None) or getattr(assigned_class_obj, "grade", None) or assigned_class_obj.name,
                "section": getattr(assigned_class_obj, "section", None) or "",
                "is_substitute": is_substitute,
                "substitute_reason": sub_reason,
                "total_students": total_students_c,
                "boys_count": boys_count,
                "girls_count": girls_count,
                "attendance_status": att_status,
                "attendance_submitted": att_marked,
                "submitted_at": submitted_at,
                "present_count": pres_c,
                "absent_count": abs_c,
                "late_count": late_c,
                "excused_count": exc_c,
                "timetable": [
                    {
                        "id": tt.id,
                        "day": tt.day,
                        "start_time": tt.start_time,
                        "end_time": tt.end_time,
                        "subject_name": subj_map.get(tt.subject_id, "—"),
                        "room": tt.room or "Main Classroom",
                    }
                    for tt in c_timetables
                ],
            }

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
        "assigned_class": assigned_class_info,
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

        # Class teacher or active substitute authorization check
        req_date_str = request.args.get("date") if request.method == "GET" else ((request.get_json(silent=True) or {}).get("date"))
        try:
            target_date = datetime.datetime.strptime(req_date_str, "%Y-%m-%d").date() if req_date_str else datetime.date.today()
        except (ValueError, TypeError):
            target_date = datetime.date.today()

        designated_alloc = ClassTeacherAllocation.query.filter_by(
            school_id=school_id, class_id=class_id, status="active"
        ).first()
        designated_tid = designated_alloc.teacher_id if designated_alloc else school_class.class_teacher_id
        is_designated = bool(designated_tid is not None and designated_tid == teacher_rec.id)

        is_substitute = False
        sub = SubstituteAllocation.query.filter(
            SubstituteAllocation.school_id == school_id,
            SubstituteAllocation.class_id == class_id,
            SubstituteAllocation.substitute_teacher_id == teacher_rec.id,
            SubstituteAllocation.is_active.is_(True),
            SubstituteAllocation.start_date <= target_date,
            SubstituteAllocation.end_date >= target_date,
        ).first()
        if sub:
            is_substitute = True

        if designated_tid is not None:
            if teacher_rec.id != designated_tid and not is_substitute:
                return jsonify({"error": "You are not the designated class teacher or active substitute for this class."}), 403
        else:
            assigned_cids, _, _ = get_teacher_assigned_classes_and_subjects(teacher_rec.id, school_id)
            if class_id not in assigned_cids and not is_substitute:
                return jsonify({"error": "You are not the designated class teacher or active substitute for this class."}), 403

        if request.method == "POST":
            settings = SMSSettings.query.filter_by(school_id=school_id).first()
            window_hours = settings.attendance_correction_window_hours if settings else 24
            days_diff = (datetime.date.today() - target_date).days
            if days_diff > 0 and (days_diff * 24) > window_hours:
                return jsonify({
                    "error": "The daily attendance register for this date is closed (past the allowed correction window). Please contact a school administrator to request an attendance correction."
                }), 403

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
    records = data.get("records") or data.get("attendance") or {}
    allow_edit = bool(data.get("allow_edit", False))

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format."}), 400

    existing_count = Attendance.query.filter_by(school_id=school_id, class_id=class_id, date=date_obj).count()
    if existing_count > 0:
        if not allow_edit:
            return jsonify({
                "error": "Attendance has already been recorded for this class on this date. Please unlock edit mode to make changes.",
                "already_recorded": True,
            }), 409
        # Teachers cannot modify another teacher's attendance record unless designated or active substitute
        if current_user.role == "teacher" and teacher_rec:
            first_rec = Attendance.query.filter_by(school_id=school_id, class_id=class_id, date=date_obj).first()
            if first_rec and first_rec.recorded_by_id and first_rec.recorded_by_id != teacher_rec.id:
                if not is_designated and not is_substitute:
                    return jsonify({
                        "error": "This attendance register was recorded by another teacher. Only the original teacher or an administrator may modify it."
                    }), 403

    now_utc = utc_now()
    present_c = 0
    absent_c = 0
    remarks_map = data.get("remarks") or {}
    for s in students:
        status = records.get(str(s.id)) or records.get(s.id) or "Present"
        if status not in ("Present", "Absent", "Late", "Excused", "Sick"):
            status = "Present"
        if status in ("Present", "Late"):
            present_c += 1
        else:
            absent_c += 1

        student_remark = remarks_map.get(str(s.id)) or remarks_map.get(s.id)

        rec = Attendance.query.filter_by(school_id=school_id, student_id=s.id, date=date_obj).first()
        was_already_alerted = bool(rec and rec.status == status)

        if rec:
            rec.status = status
            if student_remark is not None:
                rec.remarks = student_remark
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
                    remarks=student_remark,
                    recorded_by_id=teacher_rec.id if teacher_rec else current_user.id,
                    updated_at=now_utc,
                )
            )

        # Avoid duplicate alerts: only dispatch if entering Absent/Sick status anew
        if status in ("Absent", "Sick") and not was_already_alerted:
            parent_ids = set()
            if s.parent_id:
                parent_ids.add(s.parent_id)
            ps_links = ParentStudent.query.filter_by(school_id=school_id, student_id=s.id).all()
            for psl in ps_links:
                parent_ids.add(psl.parent_id)
            for pid in parent_ids:
                parent = db.session.get(Parent, pid)
                if parent and parent.user_id:
                    send_notification(
                        parent.user_id,
                        school_id,
                        f"Attendance Alert: {s.first_name} {s.last_name} was marked {status.lower()} on {date_obj.isoformat()}.",
                        "attendance",
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
        "saved": len(students),
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
            r.student_id: {
                "marks": r.marks,
                "status": getattr(r, "status", "published") or "published",
                "remarks": getattr(r, "remarks", "") or "",
            }
            for r in Result.query.filter_by(school_id=school_id, subject_id=subject_id, exam_id=exam_id).all()
        }
        overall_status = "unrecorded"
        if existing:
            statuses = [v["status"] for v in existing.values()]
            if all(st == "published" for st in statuses):
                overall_status = "published"
            elif any(st == "submitted" for st in statuses):
                overall_status = "submitted"
            else:
                overall_status = "draft"

        return jsonify({
            "subject_name": subject.name,
            "exam_name": exam.name,
            "overall_status": overall_status,
            "students": [
                {
                    "id": s.id,
                    "admission_no": s.admission_no,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "marks": existing[s.id]["marks"] if s.id in existing else "",
                    "remarks": existing[s.id]["remarks"] if s.id in existing else "",
                    "status": existing[s.id]["status"] if s.id in existing else "draft",
                    "grade": calculate_grade(existing[s.id]["marks"]) if s.id in existing else "—",
                }
                for s in students
            ],
        })

    data = request.get_json(silent=True) or {}
    marks_map = data.get("marks") or {}
    remarks_map = data.get("remarks") or {}
    action = data.get("action") or "submit_for_approval"
    target_status = "draft" if action == "save_draft" else "submitted"
    saved_count = 0
    student_ids = [s.id for s in students]

    # Lock check: Teachers cannot modify batches that are currently under review or already published
    if current_user.role == "teacher":
        locked_res = Result.query.filter(
            Result.school_id == school_id,
            Result.subject_id == subject_id,
            Result.exam_id == exam_id,
            Result.student_id.in_(student_ids),
            Result.status.in_(["submitted", "published"]),
        ).first()
        if locked_res:
            if locked_res.status == "submitted":
                return jsonify({
                    "error": "This examination batch is currently submitted for administrator review and locked. Contact your school administrator to request revisions."
                }), 403
            elif locked_res.status == "published":
                return jsonify({
                    "error": "These examination marks have already been approved and published. Published results cannot be modified without administrator authorization."
                }), 403

    if not marks_map and target_status == "submitted":
        existing_res_list = Result.query.filter(
            Result.school_id == school_id,
            Result.subject_id == subject_id,
            Result.exam_id == exam_id,
            Result.student_id.in_(student_ids),
        ).all()
        for r in existing_res_list:
            r.status = "submitted"
            saved_count += 1

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

        student_remark = remarks_map.get(str(s.id)) or remarks_map.get(s.id)

        existing_res = Result.query.filter_by(
            school_id=school_id, student_id=s.id, subject_id=subject_id, exam_id=exam_id
        ).first()
        if existing_res:
            existing_res.marks = score
            existing_res.status = target_status
            if student_remark is not None:
                existing_res.remarks = student_remark
        else:
            db.session.add(
                Result(
                    school_id=school_id,
                    student_id=s.id,
                    subject_id=subject_id,
                    exam_id=exam_id,
                    marks=score,
                    status=target_status,
                    remarks=student_remark,
                )
            )
        saved_count += 1

    if target_status == "submitted" and saved_count == 0:
        return jsonify({"error": "Cannot submit an empty examination batch for approval. Please enter at least one mark."}), 400

    status_label = "draft saved" if target_status == "draft" else "submitted for administrator review"
    record_activity(
        "exam",
        "results_recorded",
        f"Examination marks ({status_label}) for {subject.name} ({exam.name}) — {saved_count} student record(s).",
        school_id=school_id,
        target_type="exam",
        target_id=exam.name,
        commit=False,
    )
    if target_status == "submitted":
        admin_user = User.query.filter_by(school_id=school_id, role="admin").first()
        if admin_user:
            send_notification(
                admin_user.id,
                school_id,
                f"New exam marks submitted for approval: {subject.name} ({exam.name}) - {saved_count} student(s).",
                "exam",
            )
    db.session.commit()
    return jsonify({
        "message": f"Saved {saved_count} mark(s) as {target_status}.",
        "status": target_status,
    })


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
    # Only show published / approved examination marks to students
    results = (
        Result.query.filter_by(school_id=school_id, student_id=stu.id)
        .filter(Result.status.in_(["published", "approved"]) | Result.status.is_(None))
        .all()
    )
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
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
    subj_map = {s.id: s.name for s in Subject.query.filter_by(school_id=school_id).all()}
    term_map = {t.id: t.name for t in terms}

    # Attendance statistics
    att_records = Attendance.query.filter_by(school_id=school_id, student_id=stu.id).order_by(Attendance.date.desc()).all()
    pres_c = sum(1 for a in att_records if a.status in ("Present", "Late"))
    abs_c = sum(1 for a in att_records if a.status in ("Absent", "Sick", "Excused"))
    tot_d = len(att_records)
    att_rate = round(pres_c / tot_d * 100, 1) if tot_d > 0 else 100.0

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
                "teacher_name": teacher_map.get(tt.teacher_id, "—"),
                "room": tt.room or "Main Classroom",
            }
            for tt in timetable
        ],
        "attendance": {
            "present": pres_c,
            "absent": abs_c,
            "total": tot_d,
            "rate": att_rate,
            "records": [
                {
                    "date": a.date.isoformat(),
                    "status": a.status,
                    "remarks": a.remarks or "",
                }
                for a in att_records[:20]
            ],
        },
        "terms": [
            {
                "id": t.id,
                "name": t.name,
                "is_active": t.is_active,
            }
            for t in terms
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
        # Only show published / approved examination marks to parents
        results = (
            Result.query.filter_by(school_id=school_id, student_id=child.id)
            .filter(Result.status.in_(["published", "approved"]) | Result.status.is_(None))
            .all()
        )
        att_records = (
            Attendance.query.filter_by(school_id=school_id, student_id=child.id)
            .order_by(Attendance.date.desc())
            .limit(30)
            .all()
        )
        pres_c = sum(1 for a in att_records if a.status in ("Present", "Late"))
        abs_c = sum(1 for a in att_records if a.status in ("Absent", "Sick", "Excused"))
        tot_d = len(att_records)
        att_rate = round(pres_c / tot_d * 100, 1) if tot_d > 0 else 100.0

        child_timetable = Timetable.query.filter_by(school_id=school_id, class_id=child.class_id).all()
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
                    "remarks": a.remarks or "",
                }
                for a in att_records
            ],
            "attendance_stats": {
                "present": pres_c,
                "absent": abs_c,
                "total": tot_d,
                "rate": att_rate,
            },
            "timetable": [
                {
                    "id": tt.id,
                    "day": tt.day,
                    "start_time": tt.start_time,
                    "end_time": tt.end_time,
                    "subject_name": subj_map.get(tt.subject_id, "—"),
                    "room": tt.room or "Main Classroom",
                }
                for tt in child_timetable
            ],
            "terms": [
                {
                    "id": t.id,
                    "name": t.name,
                }
                for t in terms
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


# ══════════════════════════════════════════════════════════════════
#  EXTENDED SMS ROLE ENDPOINTS: ATTENDANCE, EXAM APPROVALS, SETTINGS
# ══════════════════════════════════════════════════════════════════

@api.route("/admin/attendance/overview", methods=["GET"])
@login_required
def api_admin_attendance_overview():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    date_str = request.args.get("date") or datetime.date.today().isoformat()
    class_id = request.args.get("class_id", type=int)

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        date_obj = datetime.date.today()

    students_query = Student.query.filter_by(school_id=school_id, status="active")
    if class_id:
        students_query = students_query.filter_by(class_id=class_id)
    students = students_query.order_by(Student.first_name.asc()).all()

    att_query = Attendance.query.filter_by(school_id=school_id, date=date_obj)
    if class_id:
        att_query = att_query.filter_by(class_id=class_id)
    att_records = att_query.all()
    att_map = {a.student_id: a for a in att_records}

    classes = SchoolClass.query.filter_by(school_id=school_id, is_active=True).all()
    class_map = {c.id: c.name for c in classes}
    parents = Parent.query.filter_by(school_id=school_id).all()
    parent_map = {p.id: p.phone for p in parents}

    present_count = sum(1 for a in att_records if a.status in ("Present", "Late"))
    absent_count = sum(1 for a in att_records if a.status == "Absent")
    late_count = sum(1 for a in att_records if a.status == "Late")
    excused_count = sum(1 for a in att_records if a.status == "Excused")
    sick_count = sum(1 for a in att_records if a.status == "Sick")
    total_marked = len(att_records)
    total_students = len(students)
    rate = round((present_count / total_marked) * 100, 1) if total_marked > 0 else 0.0

    student_rows = []
    absent_list = []
    for s in students:
        a = att_map.get(s.id)
        current_status = a.status if a else "Unmarked"
        remarks = a.remarks if a else ""
        row = {
            "id": s.id,
            "admission_no": s.admission_no,
            "name": f"{s.first_name} {s.last_name}",
            "class_id": s.class_id,
            "class_name": class_map.get(s.class_id, "—"),
            "status": current_status,
            "remarks": remarks or "",
            "guardian_phone": parent_map.get(s.parent_id, "No contact on file"),
            "attendance_id": a.id if a else None,
        }
        student_rows.append(row)
        if current_status in ("Absent", "Sick", "Excused"):
            absent_list.append(row)

    # Class Teacher Attendance Monitoring calculation
    all_active_classes = SchoolClass.query.filter_by(school_id=school_id, is_active=True).all()
    teachers_list = Teacher.query.filter_by(school_id=school_id).all()
    teacher_by_id = {t.id: t for t in teachers_list}

    # Fetch active allocations
    active_alloc_map = {
        a.class_id: a.teacher_id
        for a in ClassTeacherAllocation.query.filter_by(school_id=school_id, status="active").all()
    }
    # Active substitutes today
    active_sub_map = {
        s.class_id: s.substitute_teacher_id
        for s in SubstituteAllocation.query.filter(
            SubstituteAllocation.school_id == school_id,
            SubstituteAllocation.is_active.is_(True),
            SubstituteAllocation.start_date <= date_obj,
            SubstituteAllocation.end_date >= date_obj,
        ).all()
    }

    class_monitoring = []
    classes_with_teachers = 0
    classes_without_teachers = 0
    submitted_classes_count = 0
    pending_classes_count = 0
    teachers_not_submitted = []

    for cl in all_active_classes:
        assigned_tid = active_alloc_map.get(cl.id) or cl.class_teacher_id
        is_sub = cl.id in active_sub_map
        effective_tid = active_sub_map.get(cl.id) or assigned_tid
        effective_teacher = teacher_by_id.get(effective_tid)

        if assigned_tid or is_sub:
            classes_with_teachers += 1
        else:
            classes_without_teachers += 1

        cl_students = Student.query.filter_by(school_id=school_id, class_id=cl.id, status="active").all()
        cl_tot = len(cl_students)
        cl_att = Attendance.query.filter_by(school_id=school_id, class_id=cl.id, date=date_obj).all()
        cl_marked = len(cl_att)

        if cl_marked == 0:
            c_status = "not_started"
            pending_classes_count += 1
            if effective_teacher:
                teachers_not_submitted.append({
                    "class_id": cl.id,
                    "class_name": cl.name,
                    "teacher_id": effective_teacher.id,
                    "teacher_name": f"{effective_teacher.first_name} {effective_teacher.last_name}",
                    "teacher_phone": effective_teacher.phone or "",
                    "teacher_email": effective_teacher.email or "",
                    "is_substitute": is_sub,
                })
        elif cl_marked < cl_tot and cl_tot > 0:
            c_status = "in_progress"
            pending_classes_count += 1
            if effective_teacher:
                teachers_not_submitted.append({
                    "class_id": cl.id,
                    "class_name": cl.name,
                    "teacher_id": effective_teacher.id,
                    "teacher_name": f"{effective_teacher.first_name} {effective_teacher.last_name}",
                    "teacher_phone": effective_teacher.phone or "",
                    "teacher_email": effective_teacher.email or "",
                    "is_substitute": is_sub,
                })
        else:
            c_status = "submitted"
            submitted_classes_count += 1

        first_rec = cl_att[0] if cl_att else None
        c_sub_time = first_rec.updated_at.isoformat() if (first_rec and first_rec.updated_at) else None

        class_monitoring.append({
            "class_id": cl.id,
            "class_name": cl.name,
            "status": c_status,
            "teacher_name": f"{effective_teacher.first_name} {effective_teacher.last_name}" if effective_teacher else "Unassigned",
            "is_substitute": is_sub,
            "total_students": cl_tot,
            "marked_students": cl_marked,
            "present_count": sum(1 for a in cl_att if a.status in ("Present", "Late")),
            "absent_count": sum(1 for a in cl_att if a.status in ("Absent", "Sick")),
            "late_count": sum(1 for a in cl_att if a.status == "Late"),
            "submitted_at": c_sub_time,
        })

    return jsonify({
        "date": date_obj.isoformat(),
        "class_id": class_id,
        "classes": [{"id": c.id, "name": c.name} for c in classes],
        "summary": {
            "total_students": total_students,
            "total_marked": total_marked,
            "present_count": present_count,
            "absent_count": absent_count,
            "late_count": late_count,
            "excused_count": excused_count,
            "sick_count": sick_count,
            "attendance_rate": rate,
            "total_classes": len(all_active_classes),
            "classes_with_teachers": classes_with_teachers,
            "classes_without_teachers": classes_without_teachers,
            "submitted_classes_count": submitted_classes_count,
            "pending_classes_count": pending_classes_count,
        },
        "class_monitoring": class_monitoring,
        "teachers_not_submitted": teachers_not_submitted,
        "students": student_rows,
        "absent_today": absent_list,
    })


@api.route("/admin/attendance/correct", methods=["POST"])
@login_required
def api_admin_attendance_correct():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form

    try:
        student_id = int(data.get("student_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Valid student ID is required."}), 400

    date_str = (data.get("date") or "").strip()
    status = (data.get("status") or "").strip()
    remarks = (data.get("remarks") or "").strip()
    reason = (data.get("reason") or "").strip()

    if not reason:
        return jsonify({"error": "An administrative reason is required for attendance audit records."}), 400

    if status not in ("Present", "Absent", "Late", "Excused", "Sick"):
        return jsonify({"error": "Invalid attendance status."}), 400

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Expected YYYY-MM-DD."}), 400

    student = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()

    rec = Attendance.query.filter_by(school_id=school_id, student_id=student.id, date=date_obj).first()
    old_status = rec.status if rec else "Unmarked"
    effective_remarks = remarks if remarks else reason

    if rec:
        rec.status = status
        rec.remarks = effective_remarks
        rec.recorded_by_id = current_user.id
        rec.updated_at = utc_now()
    else:
        rec = Attendance(
            school_id=school_id,
            student_id=student.id,
            class_id=student.class_id,
            date=date_obj,
            status=status,
            remarks=effective_remarks,
            recorded_by_id=current_user.id,
            updated_at=utc_now(),
        )
        db.session.add(rec)

    record_activity(
        "attendance",
        "attendance_corrected",
        f"Attendance corrected for {student.first_name} {student.last_name} ({date_obj.isoformat()}): from '{old_status}' to '{status}'. Reason: {reason}",
        school_id=school_id,
        actor_user=current_user,
        target_type="student",
        target_id=student.id,
        metadata={"old_status": old_status, "new_status": status, "reason": reason},
        commit=True,
    )

    return jsonify({
        "message": f"Attendance successfully updated to {status}.",
        "student_id": student.id,
        "date": date_obj.isoformat(),
        "status": status,
        "remarks": remarks,
    })


@api.route("/admin/results/pending", methods=["GET"])
@login_required
def api_admin_results_pending():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    # Query results awaiting approval
    pending_results = (
        Result.query.filter_by(school_id=school_id, status="submitted")
        .all()
    )

    grouped = {}
    for r in pending_results:
        key = (r.exam_id, r.subject_id)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    classes = SchoolClass.query.filter_by(school_id=school_id).all()
    class_map = {c.id: c.name for c in classes}
    subjects = Subject.query.filter_by(school_id=school_id).all()
    subj_map = {s.id: s.name for s in subjects}
    exams = Exam.query.filter_by(school_id=school_id).all()
    exam_map = {e.id: e for e in exams}

    batches = []
    for (exam_id, subject_id), res_list in grouped.items():
        exam_obj = exam_map.get(exam_id)
        first_r = res_list[0]
        st_obj = db.session.get(Student, first_r.student_id)
        class_id = st_obj.class_id if st_obj else None
        avg_score = round(sum(r.marks for r in res_list) / len(res_list), 1)

        batches.append({
            "exam_id": exam_id,
            "exam_name": exam_obj.name if exam_obj else "—",
            "subject_id": subject_id,
            "subject_name": subj_map.get(subject_id, "—"),
            "class_id": class_id,
            "class_name": class_map.get(class_id, "—") if class_id else "—",
            "student_count": len(res_list),
            "average_score": avg_score,
            "submitted_at": first_r.updated_at.isoformat() if getattr(first_r, "updated_at", None) else None,
        })

    return jsonify({
        "pending_batches": batches,
        "total_pending_records": len(pending_results),
    })


@api.route("/admin/results/approve", methods=["POST"])
@login_required
def api_admin_results_approve():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form

    try:
        exam_id = int(data.get("exam_id"))
        subject_id = int(data.get("subject_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Exam ID and Subject ID are required."}), 400

    class_id = data.get("class_id")
    action = data.get("action") or "approve_publish"  # "approve_publish" or "reject_to_draft"

    query = Result.query.filter_by(school_id=school_id, exam_id=exam_id, subject_id=subject_id)
    if class_id:
        student_ids = [s.id for s in Student.query.filter_by(school_id=school_id, class_id=int(class_id)).all()]
        query = query.filter(Result.student_id.in_(student_ids))

    results = query.all()
    if not results:
        return jsonify({"error": "No matching examination records found to process."}), 404

    exam = db.session.get(Exam, exam_id)
    subject = db.session.get(Subject, subject_id)

    feedback = (data.get("feedback") or data.get("reason") or data.get("notes") or "").strip()
    target_status = "published" if action in ("approve", "approve_publish") else "draft"
    for r in results:
        r.status = target_status
        if target_status == "draft" and feedback:
            r.remarks = f"Returned for revision: {feedback}"
        r.updated_at = utc_now()

    if target_status == "published":
        # Create notifications for students and parents
        for r in results:
            s = db.session.get(Student, r.student_id)
            if s and s.user_id:
                send_notification(
                    s.user_id,
                    school_id,
                    f"Exam Results Published: {subject.name if subject else 'Subject'} ({exam.name if exam else 'Exam'}) - Score: {r.marks}",
                    "exam",
                )
            # Notify parents (via foreign key or junction table)
            parent_ids = set()
            if s and s.parent_id:
                parent_ids.add(s.parent_id)
            if s:
                ps_links = ParentStudent.query.filter_by(school_id=school_id, student_id=s.id).all()
                for psl in ps_links:
                    parent_ids.add(psl.parent_id)
            for pid in parent_ids:
                parent = db.session.get(Parent, pid)
                if parent and parent.user_id:
                    send_notification(
                        parent.user_id,
                        school_id,
                        f"Exam Results Published for {s.first_name}: {subject.name if subject else 'Subject'} ({exam.name if exam else 'Exam'}) - Score: {r.marks}",
                        "exam",
                    )
    elif target_status == "draft":
        # Notify the assigned teacher with administrative feedback
        teacher_assign = TeacherAssignment.query.filter_by(
            school_id=school_id,
            class_id=int(class_id) if class_id else None,
            subject_id=subject_id,
        ).first() if class_id else None
        teacher_uid = None
        if teacher_assign and teacher_assign.teacher and teacher_assign.teacher.user_id:
            teacher_uid = teacher_assign.teacher.user_id
        if teacher_uid:
            msg = f"Results for {subject.name if subject else 'Subject'} ({exam.name if exam else 'Exam'}) were returned for revision."
            if feedback:
                msg += f" Note: {feedback}"
            send_notification(teacher_uid, school_id, msg, "exam")

    record_activity(
        "exam",
        "results_approved" if target_status == "published" else "results_rejected_to_draft",
        f"Examination marks ({target_status}) for {subject.name if subject else 'Subject'} ({exam.name if exam else 'Exam'}) — {len(results)} student(s).",
        school_id=school_id,
        actor_user=current_user,
        target_type="exam",
        target_id=exam.name if exam else str(exam_id),
        commit=True,
    )

    action_label = "approved and published" if target_status == "published" else "returned to draft status for revision"
    return jsonify({
        "message": f"Successfully {action_label} {len(results)} student examination record(s).",
        "status": target_status,
        "count": len(results),
    })


@api.route("/admin/results/overview", methods=["GET"])
@login_required
def api_admin_results_overview():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    exam_id = request.args.get("exam_id", type=int)
    class_id = request.args.get("class_id", type=int)
    subject_id = request.args.get("subject_id", type=int)

    query = Result.query.filter_by(school_id=school_id)
    if exam_id:
        query = query.filter_by(exam_id=exam_id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    if class_id:
        student_ids = [s.id for s in Student.query.filter_by(school_id=school_id, class_id=class_id).all()]
        query = query.filter(Result.student_id.in_(student_ids))

    results = query.all()

    students = Student.query.filter_by(school_id=school_id).all()
    student_map = {s.id: s for s in students}
    subjects = Subject.query.filter_by(school_id=school_id).all()
    subj_map = {s.id: s.name for s in subjects}
    exams = Exam.query.filter_by(school_id=school_id).all()
    exam_map = {e.id: e.name for e in exams}
    classes = SchoolClass.query.filter_by(school_id=school_id).all()
    class_map = {c.id: c.name for c in classes}

    rows = []
    for r in results:
        s = student_map.get(r.student_id)
        rows.append({
            "id": r.id,
            "student_id": r.student_id,
            "admission_no": s.admission_no if s else "—",
            "student_name": f"{s.first_name} {s.last_name}" if s else "—",
            "class_name": class_map.get(s.class_id, "—") if s else "—",
            "exam_id": r.exam_id,
            "exam_name": exam_map.get(r.exam_id, "—"),
            "subject_id": r.subject_id,
            "subject_name": subj_map.get(r.subject_id, "—"),
            "marks": r.marks,
            "grade": calculate_grade(r.marks),
            "status": getattr(r, "status", "published") or "published",
            "remarks": getattr(r, "remarks", "") or "",
        })

    avg_score = round(sum(r.marks for r in results) / len(results), 1) if results else 0.0
    pass_count = sum(1 for r in results if r.marks >= 50)
    fail_count = sum(1 for r in results if r.marks < 50)

    return jsonify({
        "results": rows,
        "count": len(rows),
        "average": avg_score,
        "pass_count": pass_count,
        "fail_count": fail_count,
    })


@api.route("/admin/report-cards", methods=["GET"])
@login_required
def api_admin_report_cards():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    class_id = request.args.get("class_id", type=int)
    term_id = request.args.get("term_id", type=int)

    classes = SchoolClass.query.filter_by(school_id=school_id, is_active=True).all()
    terms = Term.query.filter_by(school_id=school_id).all()

    if not class_id and classes:
        class_id = classes[0].id
    if not term_id and terms:
        term_id = terms[0].id

    students = Student.query.filter_by(school_id=school_id, class_id=class_id, status="active").order_by(Student.first_name.asc()).all()

    student_cards = []
    student_scores = {}
    for s in students:
        res = (
            Result.query.join(Exam)
            .filter(
                Result.school_id == school_id,
                Result.student_id == s.id,
                Exam.term_id == term_id,
                Result.status.in_(["published", "approved"]) | Result.status.is_(None),
            )
            .all()
        )
        total = sum(r.marks for r in res) if res else 0.0
        avg = round(total / len(res), 1) if res else 0.0
        student_scores[s.id] = avg

    sorted_ranks = sorted(student_scores.items(), key=lambda x: x[1], reverse=True)
    rank_map = {sid: idx + 1 for idx, (sid, _) in enumerate(sorted_ranks)}

    for s in students:
        avg = student_scores.get(s.id, 0.0)
        grade = calculate_grade(avg) if avg > 0 else "—"
        student_cards.append({
            "id": s.id,
            "admission_no": s.admission_no,
            "name": f"{s.first_name} {s.last_name}",
            "average": avg,
            "final_grade": grade,
            "class_rank": rank_map.get(s.id, 1),
            "class_size": len(students),
            "pdf_url": f"/student/report-card/{s.id}/{term_id}",
        })

    return jsonify({
        "class_id": class_id,
        "term_id": term_id,
        "classes": [{"id": c.id, "name": c.name} for c in classes],
        "terms": [{"id": t.id, "name": t.name} for t in terms],
        "student_cards": student_cards,
    })


@api.route("/admin/settings", methods=["GET", "POST"])
@login_required
def api_admin_settings():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    school = db.session.get(School, school_id)
    if not school:
        return jsonify({"error": "School not found."}), 404

    if request.method == "GET":
        return jsonify({
            "id": school.id,
            "name": school.name,
            "subdomain": school.subdomain,
            "email": school.email,
            "phone": school.phone or "",
            "address": school.address or "",
            "logo_url": school.logo_url or "",
            "currency": getattr(school, "currency", "ZMW") or "ZMW",
            "plan": school.plan,
            "billing_cycle": school.billing_cycle,
            "subscription_ends_at": school.subscription_ends_at.isoformat() if school.subscription_ends_at else None,
        })

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    address = (data.get("address") or "").strip()
    logo_url = (data.get("logo_url") or "").strip()
    currency = (data.get("currency") or "ZMW").strip().upper()

    if name:
        school.name = name
    if phone:
        school.phone = phone
    school.address = address
    school.logo_url = logo_url
    if currency in ("ZMW", "USD", "EUR", "GBP", "KES", "ZAR"):
        school.currency = currency

    record_activity(
        "school",
        "settings_updated",
        f"School settings and profile updated by '{current_user.username}'.",
        school_id=school_id,
        actor_user=current_user,
        target_type="school",
        target_id=school.id,
        commit=True,
    )

    return jsonify({
        "message": "School settings saved successfully.",
        "school": {
            "id": school.id,
            "name": school.name,
            "subdomain": school.subdomain,
            "email": school.email,
            "phone": school.phone,
            "address": school.address,
            "logo_url": school.logo_url,
            "currency": school.currency,
        },
    })


@api.route("/teacher/timetable", methods=["GET"])
@login_required
def api_teacher_timetable():
    err = _require_role("teacher", "admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
    if not teacher_rec and current_user.role == "teacher":
        return jsonify({"timetable": []})

    teacher_id = teacher_rec.id if teacher_rec else request.args.get("teacher_id", type=int)

    query = Timetable.query.filter_by(school_id=school_id, is_active=True)
    if teacher_id:
        query = query.filter_by(teacher_id=teacher_id)
    timetables = query.order_by(Timetable.start_time.asc()).all()

    classes = SchoolClass.query.filter_by(school_id=school_id).all()
    class_map = {c.id: c.name for c in classes}
    subjects = Subject.query.filter_by(school_id=school_id).all()
    subj_map = {s.id: s.name for s in subjects}

    entries = [
        {
            "id": tt.id,
            "day": tt.day,
            "start_time": tt.start_time,
            "end_time": tt.end_time,
            "class_id": tt.class_id,
            "class_name": class_map.get(tt.class_id, "—"),
            "subject_id": tt.subject_id,
            "subject_name": subj_map.get(tt.subject_id, "—"),
            "room": tt.room or "Main Classroom",
        }
        for tt in timetables
    ]
    by_day = {}
    for entry in entries:
        by_day.setdefault(entry["day"], []).append(entry)

    return jsonify({
        "timetable": entries,
        "by_day": by_day,
    })


@api.route("/student/timetable", methods=["GET"])
@login_required
def api_student_timetable():
    err = _require_role("student")
    if err:
        return err
    school_id = get_current_school_id()

    stu = None
    if current_user.student_id:
        stu = Student.query.filter_by(id=current_user.student_id, school_id=school_id).first()
    if not stu:
        stu = Student.query.filter_by(school_id=school_id, admission_no=current_user.username).first()
    if not stu or not stu.class_id:
        return jsonify({"timetable": []})

    timetables = Timetable.query.filter_by(school_id=school_id, class_id=stu.class_id, is_active=True).order_by(Timetable.start_time.asc()).all()
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
    subjects = Subject.query.filter_by(school_id=school_id).all()
    subj_map = {s.id: s.name for s in subjects}

    return jsonify({
        "timetable": [
            {
                "id": tt.id,
                "day": tt.day,
                "start_time": tt.start_time,
                "end_time": tt.end_time,
                "subject_name": subj_map.get(tt.subject_id, "—"),
                "teacher_name": teacher_map.get(tt.teacher_id, "—"),
                "room": tt.room or "Main Classroom",
            }
            for tt in timetables
        ]
    })


@api.route("/student/attendance", methods=["GET"])
@login_required
def api_student_attendance():
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
        return jsonify({"error": "Student not found."}), 404

    records = Attendance.query.filter_by(school_id=school_id, student_id=stu.id).order_by(Attendance.date.desc()).all()
    present_c = sum(1 for a in records if a.status in ("Present", "Late"))
    absent_c = sum(1 for a in records if a.status in ("Absent", "Sick", "Excused"))
    late_c = sum(1 for a in records if a.status == "Late")
    excused_c = sum(1 for a in records if a.status == "Excused")
    sick_c = sum(1 for a in records if a.status == "Sick")
    tot = len(records)
    rate = round((present_c / tot) * 100, 1) if tot > 0 else 100.0

    return jsonify({
        "summary": {
            "total_days": tot,
            "present_days": present_c,
            "absent_days": absent_c,
            "late_days": late_c,
            "excused_days": excused_c,
            "sick_days": sick_c,
            "attendance_rate": rate,
        },
        "records": [
            {
                "id": a.id,
                "date": a.date.isoformat(),
                "status": a.status,
                "remarks": a.remarks or "",
            }
            for a in records[:60]
        ],
    })


@api.route("/parent/child/<int:child_id>/timetable", methods=["GET"])
@login_required
def api_parent_child_timetable(child_id):
    err = _require_role("parent")
    if err:
        return err
    school_id = get_current_school_id()

    parent = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first_or_404()
    link = ParentStudent.query.filter_by(school_id=school_id, parent_id=parent.id, student_id=child_id).first()
    if not link:
        return jsonify({"error": "You are not authorized to view records for this child."}), 403

    child = db.session.get(Student, child_id)
    if not child or not child.class_id:
        return jsonify({"timetable": []})

    timetables = Timetable.query.filter_by(school_id=school_id, class_id=child.class_id, is_active=True).order_by(Timetable.start_time.asc()).all()
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
    subjects = Subject.query.filter_by(school_id=school_id).all()
    subj_map = {s.id: s.name for s in subjects}

    return jsonify({
        "child_id": child.id,
        "child_name": f"{child.first_name} {child.last_name}",
        "timetable": [
            {
                "id": tt.id,
                "day": tt.day,
                "start_time": tt.start_time,
                "end_time": tt.end_time,
                "subject_name": subj_map.get(tt.subject_id, "—"),
                "teacher_name": teacher_map.get(tt.teacher_id, "—"),
                "room": tt.room or "Main Classroom",
            }
            for tt in timetables
        ]
    })




# -----------------------------------------------------------------------------
# CLASS TEACHER ALLOCATION, SUBSTITUTE ALLOCATION & SUBJECT ATTENDANCE
# -----------------------------------------------------------------------------

@api.route("/teacher/subject-attendance/<int:class_id>/<int:subject_id>", methods=["GET", "POST"])
@login_required
def api_teacher_subject_attendance(class_id, subject_id):
    err = _require_role("teacher", "admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()
    subject = Subject.query.filter_by(id=subject_id, school_id=school_id).first_or_404()

    teacher_rec = None
    if current_user.role == "teacher":
        teacher_rec = Teacher.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not teacher_rec:
            return jsonify({"error": "No teacher profile found."}), 403

    students = Student.query.filter_by(school_id=school_id, class_id=class_id, status="active").order_by(Student.first_name.asc()).all()

    if request.method == "GET":
        date_str = request.args.get("date") or datetime.date.today().isoformat()
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            date_obj = datetime.date.today()

        records = SubjectAttendance.query.filter_by(
            school_id=school_id, class_id=class_id, subject_id=subject_id, date=date_obj
        ).all()
        rec_map = {r.student_id: r.status for r in records}
        remarks_map = {r.student_id: r.remarks for r in records}

        return jsonify({
            "class_id": school_class.id,
            "class_name": school_class.name,
            "subject_id": subject.id,
            "subject_name": subject.name,
            "date": date_obj.isoformat(),
            "already_recorded": len(records) > 0,
            "students": [
                {
                    "id": s.id,
                    "admission_no": s.admission_no,
                    "first_name": s.first_name,
                    "last_name": s.last_name,
                    "status": rec_map.get(s.id, "Present"),
                    "remarks": remarks_map.get(s.id, ""),
                }
                for s in students
            ],
        })

    data = request.get_json(silent=True) or {}
    date_str = data.get("date") or datetime.date.today().isoformat()
    raw_records = data.get("records") or {}
    remarks_dict = data.get("remarks") or {}
    period_val = data.get("period")

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format."}), 400

    now_utc = utc_now()
    for s in students:
        st = raw_records.get(str(s.id)) or raw_records.get(s.id) or "Present"
        if st not in ("Present", "Absent", "Late", "Excused", "Sick"):
            st = "Present"
        rem = remarks_dict.get(str(s.id)) or remarks_dict.get(s.id)

        rec = SubjectAttendance.query.filter_by(
            school_id=school_id, class_id=class_id, subject_id=subject_id, student_id=s.id, date=date_obj
        ).first()

        if rec:
            rec.status = st
            rec.remarks = rem
            rec.period = period_val
            rec.recorded_by_id = teacher_rec.id if teacher_rec else current_user.id
            rec.updated_at = now_utc
        else:
            db.session.add(
                SubjectAttendance(
                    school_id=school_id,
                    class_id=class_id,
                    subject_id=subject_id,
                    student_id=s.id,
                    date=date_obj,
                    period=period_val,
                    status=st,
                    remarks=rem,
                    recorded_by_id=teacher_rec.id if teacher_rec else current_user.id,
                    updated_at=now_utc,
                )
            )

    db.session.commit()
    return jsonify({"message": "Subject attendance saved successfully."}), 200


@api.route("/admin/class-teachers", methods=["GET", "POST"])
@login_required
def api_admin_class_teachers():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    if request.method == "GET":
        classes = SchoolClass.query.filter_by(school_id=school_id, is_active=True).order_by(SchoolClass.name.asc()).all()
        teachers = Teacher.query.filter_by(school_id=school_id).order_by(Teacher.first_name.asc()).all()
        teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
        staff_no_map = {t.id: t.staff_no for t in teachers}

        active_allocs = ClassTeacherAllocation.query.filter_by(school_id=school_id, status="active").all()
        allocated_teacher_ids = {a.teacher_id for a in active_allocs}
        allocated_class_ids = {a.class_id for a in active_allocs}

        # Sync existing SchoolClass.class_teacher_id into active allocations if missing
        synced = False
        for c in classes:
            if c.class_teacher_id and c.id not in allocated_class_ids:
                alloc = ClassTeacherAllocation(
                    school_id=school_id,
                    class_id=c.id,
                    teacher_id=c.class_teacher_id,
                    academic_year="2025/2026",
                    assignment_date=datetime.date.today(),
                    status="active",
                    created_by_id=current_user.id,
                )
                db.session.add(alloc)
                allocated_teacher_ids.add(c.class_teacher_id)
                allocated_class_ids.add(c.id)
                synced = True
        if synced:
            db.session.commit()

        active_allocs = ClassTeacherAllocation.query.filter_by(school_id=school_id, status="active").order_by(ClassTeacherAllocation.assignment_date.desc()).all()
        class_map = {c.id: c.name for c in classes}
        history_allocs = ClassTeacherAllocation.query.filter_by(school_id=school_id).order_by(ClassTeacherAllocation.created_at.desc()).limit(50).all()

        unallocated_classes = [
            {"id": c.id, "name": c.name}
            for c in classes if c.id not in allocated_class_ids
        ]
        unallocated_teachers = [
            {"id": t.id, "name": f"{t.first_name} {t.last_name}", "staff_no": t.staff_no, "specialization": t.subject_specialization}
            for t in teachers if t.id not in allocated_teacher_ids
        ]

        return jsonify({
            "allocations": [
                {
                    "id": a.id,
                    "academic_year": a.academic_year,
                    "class_id": a.class_id,
                    "class_name": class_map.get(a.class_id, "—"),
                    "teacher_id": a.teacher_id,
                    "teacher_name": teacher_map.get(a.teacher_id, "—"),
                    "staff_no": staff_no_map.get(a.teacher_id, "—"),
                    "assignment_date": a.assignment_date.isoformat() if a.assignment_date else None,
                    "status": a.status,
                    "previous_teacher_id": a.previous_teacher_id,
                    "previous_teacher_name": teacher_map.get(a.previous_teacher_id) if a.previous_teacher_id else None,
                    "is_override": a.is_override,
                    "override_reason": a.override_reason,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in active_allocs
            ],
            "unallocated_classes": unallocated_classes,
            "unallocated_teachers": unallocated_teachers,
            "classes": [{"id": c.id, "name": c.name} for c in classes],
            "teachers": [{"id": t.id, "name": f"{t.first_name} {t.last_name}", "staff_no": t.staff_no} for t in teachers],
            "history": [
                {
                    "id": h.id,
                    "academic_year": h.academic_year,
                    "class_name": class_map.get(h.class_id, "—"),
                    "teacher_name": teacher_map.get(h.teacher_id, "—"),
                    "status": h.status,
                    "assignment_date": h.assignment_date.isoformat() if h.assignment_date else None,
                    "is_override": h.is_override,
                    "override_reason": h.override_reason,
                }
                for h in history_allocs
            ],
        })

    data = request.get_json(silent=True) or request.form
    try:
        class_id = int(data.get("class_id"))
        teacher_id = int(data.get("teacher_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Class ID and Teacher ID are required."}), 400

    school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()
    teacher = Teacher.query.filter_by(id=teacher_id, school_id=school_id).first_or_404()

    academic_year = (data.get("academic_year") or "2025/2026").strip()
    is_override = bool(data.get("is_override", False))
    override_reason = (data.get("override_reason") or "").strip()

    # 1-class-per-teacher rule enforcement
    existing_teacher_alloc = ClassTeacherAllocation.query.filter_by(
        school_id=school_id, teacher_id=teacher_id, academic_year=academic_year, status="active"
    ).first()

    if existing_teacher_alloc and existing_teacher_alloc.class_id != class_id:
        other_class = db.session.get(SchoolClass, existing_teacher_alloc.class_id)
        other_class_name = other_class.name if other_class else "another class"
        if not is_override:
            return jsonify({
                "error": f"{teacher.first_name} {teacher.last_name} is already assigned as Class Teacher for {other_class_name}.",
                "conflict_class": other_class_name,
                "requires_override": True,
            }), 409
        if not override_reason:
            return jsonify({
                "error": "An administrative override reason is required when assigning a teacher to more than one class."
            }), 400

    # Deactivate existing active allocation for this class
    current_class_alloc = ClassTeacherAllocation.query.filter_by(
        school_id=school_id, class_id=class_id, status="active"
    ).first()
    previous_tid = None
    if current_class_alloc:
        previous_tid = current_class_alloc.teacher_id
        current_class_alloc.status = "reassigned"

    new_alloc = ClassTeacherAllocation(
        school_id=school_id,
        class_id=class_id,
        teacher_id=teacher_id,
        academic_year=academic_year,
        assignment_date=datetime.date.today(),
        status="active",
        previous_teacher_id=previous_tid,
        is_override=is_override,
        override_reason=override_reason if is_override else None,
        created_by_id=current_user.id,
    )
    db.session.add(new_alloc)
    school_class.class_teacher_id = teacher_id

    record_activity(
        "class_teacher_allocation",
        "assigned",
        f"Class Teacher assigned to {school_class.name}",
        school_id=school_id,
        metadata={"class_id": class_id, "teacher_id": teacher_id, "is_override": is_override},
    )
    db.session.commit()

    return jsonify({"message": f"Class Teacher successfully assigned to {school_class.name}."}), 201


@api.route("/admin/class-teachers/<int:allocation_id>", methods=["DELETE"])
@login_required
def api_admin_class_teacher_revoke(allocation_id):
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    alloc = ClassTeacherAllocation.query.filter_by(id=allocation_id, school_id=school_id).first_or_404()
    alloc.status = "revoked"

    school_class = db.session.get(SchoolClass, alloc.class_id)
    if school_class and school_class.class_teacher_id == alloc.teacher_id:
        school_class.class_teacher_id = None

    record_activity(
        "class_teacher_allocation",
        "revoked",
        f"Class Teacher allocation revoked for class {alloc.class_id}",
        school_id=school_id,
        metadata={"class_id": alloc.class_id, "teacher_id": alloc.teacher_id},
    )
    db.session.commit()
    return jsonify({"message": "Class Teacher allocation revoked successfully."}), 200


@api.route("/admin/substitutes", methods=["GET", "POST"])
@login_required
def api_admin_substitutes():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    if request.method == "GET":
        subs = SubstituteAllocation.query.filter_by(school_id=school_id).order_by(SubstituteAllocation.start_date.desc()).all()
        teachers = Teacher.query.filter_by(school_id=school_id).all()
        teacher_map = {t.id: f"{t.first_name} {t.last_name}" for t in teachers}
        classes = SchoolClass.query.filter_by(school_id=school_id).all()
        class_map = {c.id: c.name for c in classes}

        return jsonify({
            "substitutes": [
                {
                    "id": s.id,
                    "class_id": s.class_id,
                    "class_name": class_map.get(s.class_id, "—"),
                    "original_teacher_id": s.original_teacher_id,
                    "original_teacher_name": teacher_map.get(s.original_teacher_id, "—") if s.original_teacher_id else "None",
                    "substitute_teacher_id": s.substitute_teacher_id,
                    "substitute_teacher_name": teacher_map.get(s.substitute_teacher_id, "—"),
                    "start_date": s.start_date.isoformat(),
                    "end_date": s.end_date.isoformat(),
                    "reason": s.reason,
                    "is_active": s.is_active,
                }
                for s in subs
            ]
        })

    data = request.get_json(silent=True) or request.form
    try:
        class_id = int(data.get("class_id"))
        sub_teacher_id = int(data.get("substitute_teacher_id"))
        start_date = datetime.datetime.strptime(data.get("start_date"), "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(data.get("end_date"), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Class ID, substitute teacher ID, start date and end date are required."}), 400

    if start_date > end_date:
        return jsonify({"error": "Start date must be before or equal to end date."}), 400

    school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()
    sub_teacher = Teacher.query.filter_by(id=sub_teacher_id, school_id=school_id).first_or_404()
    reason = (data.get("reason") or "Teacher temporary leave").strip()

    sub = SubstituteAllocation(
        school_id=school_id,
        class_id=class_id,
        original_teacher_id=school_class.class_teacher_id,
        substitute_teacher_id=sub_teacher_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        authorized_by_id=current_user.id,
        is_active=True,
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify({"message": f"Substitute teacher assigned for {school_class.name}."}), 201


@api.route("/admin/substitutes/<int:sub_id>", methods=["DELETE"])
@login_required
def api_admin_substitute_deactivate(sub_id):
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    sub = SubstituteAllocation.query.filter_by(id=sub_id, school_id=school_id).first_or_404()
    sub.is_active = False
    db.session.commit()
    return jsonify({"message": "Substitute allocation deactivated."}), 200


# -----------------------------------------------------------------------------
# SMS & PARENT COMMUNICATION
# -----------------------------------------------------------------------------

@api.route("/admin/sms/settings", methods=["GET", "PUT"])
@login_required
def api_admin_sms_settings():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    if not settings:
        settings = SMSSettings(school_id=school_id)
        db.session.add(settings)
        db.session.commit()

    if request.method == "GET":
        return jsonify({
            "sms_enabled": settings.sms_enabled,
            "sender_id": settings.sender_id or "SchoolStacks",
            "fee_reminders_enabled": settings.fee_reminders_enabled,
            "fee_reminder_intervals": settings.fee_reminder_intervals or [7, 0, -7],
            "fee_reminder_template": settings.fee_reminder_template,
            "absenteeism_alerts_enabled": settings.absenteeism_alerts_enabled,
            "absenteeism_consecutive_days": settings.absenteeism_consecutive_days or 2,
            "absenteeism_cumulative_days": settings.absenteeism_cumulative_days or 5,
            "absenteeism_template": settings.absenteeism_template,
            "enable_subject_attendance": settings.enable_subject_attendance,
            "attendance_correction_window_hours": settings.attendance_correction_window_hours or 24,
            "is_dry_run": os.getenv("SMS_TO_DRY_RUN", "true").lower() in ("true", "1", "yes"),
        })

    data = request.get_json(silent=True) or request.form
    if "sms_enabled" in data:
        settings.sms_enabled = bool(data["sms_enabled"])
    if "sender_id" in data:
        settings.sender_id = (data["sender_id"] or "").strip()
    if "fee_reminders_enabled" in data:
        settings.fee_reminders_enabled = bool(data["fee_reminders_enabled"])
    if "fee_reminder_intervals" in data:
        settings.fee_reminder_intervals = data["fee_reminder_intervals"]
    if "fee_reminder_template" in data:
        settings.fee_reminder_template = data["fee_reminder_template"]
    if "absenteeism_alerts_enabled" in data:
        settings.absenteeism_alerts_enabled = bool(data["absenteeism_alerts_enabled"])
    if "absenteeism_consecutive_days" in data:
        settings.absenteeism_consecutive_days = int(data["absenteeism_consecutive_days"])
    if "absenteeism_cumulative_days" in data:
        settings.absenteeism_cumulative_days = int(data["absenteeism_cumulative_days"])
    if "absenteeism_template" in data:
        settings.absenteeism_template = data["absenteeism_template"]
    if "enable_subject_attendance" in data:
        settings.enable_subject_attendance = bool(data["enable_subject_attendance"])
    if "attendance_correction_window_hours" in data:
        settings.attendance_correction_window_hours = int(data["attendance_correction_window_hours"])

    settings.updated_at = utc_now()
    db.session.commit()
    return jsonify({"message": "SMS settings saved successfully."}), 200


@api.route("/admin/sms/send-test", methods=["POST"])
@login_required
def api_admin_sms_send_test():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    data = request.get_json(silent=True) or request.form
    phone = (data.get("phone_number") or "").strip()
    msg = (data.get("message") or "This is a test notification from SchoolStacks SMS integration.").strip()

    if not phone:
        return jsonify({"error": "Phone number is required."}), 400

    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    sender_id = settings.sender_id if settings else "SchoolStacks"

    result = send_school_sms(
        school_id=school_id,
        recipient_phone=phone,
        message_text=msg,
        message_type="test",
        recipient_type="staff",
        sender_id=sender_id,
    )
    return jsonify({
        "success": result.get("success", False),
        "status": result.get("status"),
        "error": result.get("error"),
        "provider_message_id": result.get("provider_message_id"),
        "cost": result.get("cost"),
        "dry_run": result.get("dry_run", False),
    }), 200 if result.get("success") else 400


@api.route("/admin/sms/history", methods=["GET"])
@login_required
def api_admin_sms_history():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    msg_type = request.args.get("message_type")
    status_filter = request.args.get("status")

    query = SMSMessage.query.filter_by(school_id=school_id)
    if msg_type:
        query = query.filter_by(message_type=msg_type)
    if status_filter:
        query = query.filter_by(status=status_filter)

    all_msgs = query.order_by(SMSMessage.created_at.desc()).limit(100).all()

    all_school_msgs = SMSMessage.query.filter_by(school_id=school_id).all()
    total_sent = len(all_school_msgs)
    delivered = sum(1 for m in all_school_msgs if m.status in ("delivered", "sent"))
    failed = sum(1 for m in all_school_msgs if m.status in ("failed", "undelivered"))
    pending = sum(1 for m in all_school_msgs if m.status in ("pending", "queued"))
    total_cost = sum(m.cost or 0.0 for m in all_school_msgs)

    return jsonify({
        "metrics": {
            "total_sent": total_sent,
            "delivered": delivered,
            "failed": failed,
            "pending": pending,
            "total_cost": round(total_cost, 4),
        },
        "messages": [
            {
                "id": m.id,
                "recipient_phone": m.recipient_phone,
                "recipient_name": m.recipient_name,
                "recipient_type": m.recipient_type,
                "message_type": m.message_type,
                "message_body": m.message_body,
                "status": m.status,
                "cost": m.cost,
                "provider_message_id": m.provider_message_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            }
            for m in all_msgs
        ],
    })


@api.route("/sms/webhook", methods=["POST"])
@api.route("/billing/webhook/sms-to", methods=["POST"])
def api_sms_webhook():
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    provider_msg_id = payload.get("message_id") or payload.get("id") or payload.get("messageId")
    status = (payload.get("status") or payload.get("delivery_status") or "delivered").lower()

    if provider_msg_id:
        msg = SMSMessage.query.filter_by(provider_message_id=str(provider_msg_id)).first()
        if msg:
            msg.status = status
            db.session.add(
                SMSDeliveryEvent(
                    sms_message_id=msg.id,
                    event_type=status,
                    provider_status=status,
                    payload=payload,
                )
            )
            db.session.commit()

    return jsonify({"status": "received", "provider_message_id": provider_msg_id}), 200


def _get_due_fee_reminders(school_id, filter_due_only=False):
    school = db.session.get(School, school_id)
    school_name = school.name if school else "SchoolStacks"
    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    template = settings.fee_reminder_template if (settings and settings.fee_reminder_template) else (
        "Dear Parent/Guardian, this is a reminder from {school_name} that the outstanding fee balance for {student_name} is ZMW {balance:.2f}. Due date: {due_date}. Please pay promptly."
    )

    today = datetime.date.today()
    terms = Term.query.filter_by(school_id=school_id, is_active=True).all()
    if not terms:
        terms = Term.query.filter_by(school_id=school_id).order_by(Term.start_date.desc()).limit(1).all()

    students = Student.query.filter_by(school_id=school_id, status="active").all()
    class_map = {c.id: c.name for c in SchoolClass.query.filter_by(school_id=school_id).all()}

    reminders = []
    cooldown_cutoff = utc_now() - datetime.timedelta(days=3)

    for stu in students:
        if not stu.class_id:
            continue

        parent = None
        if stu.parent_id:
            parent = db.session.get(Parent, stu.parent_id)
        if not parent:
            psl = ParentStudent.query.filter_by(school_id=school_id, student_id=stu.id).first()
            if psl:
                parent = db.session.get(Parent, psl.parent_id)

        phone = parent.phone if parent else None
        if not phone:
            continue

        try:
            norm_phone = normalize_phone_number(phone)
        except ValueError:
            continue

        for t in terms:
            fee_struct = FeeStructure.query.filter_by(
                school_id=school_id, class_id=stu.class_id, term_id=t.id
            ).first()
            if not fee_struct:
                continue

            balance = calculate_balance(stu.id, t.id, school_id)
            if balance <= 0:
                continue  # Paid or zero balance strictly excluded

            due_date = t.start_date or today
            days_diff = (today - due_date).days

            # Determine stage
            if days_diff < 0:
                stage = "Upcoming Reminder"
            elif days_diff == 0:
                stage = "Due Date Reminder"
            else:
                stage = "Overdue Notice"

            if filter_due_only:
                # 7 days before, due date (0), or 7 days after
                if days_diff not in (-7, 0, 7):
                    continue

            # Check cooldown
            recent = SMSMessage.query.filter(
                SMSMessage.school_id == school_id,
                SMSMessage.recipient_phone == norm_phone,
                SMSMessage.message_type == "fee_reminder",
                SMSMessage.created_at >= cooldown_cutoff,
            ).first()

            if recent:
                continue

            msg_text = template.format(
                school_name=school_name,
                student_name=f"{stu.first_name} {stu.last_name}",
                balance=balance,
                due_date=due_date.isoformat(),
            )

            reminders.append({
                "student_id": stu.id,
                "student_name": f"{stu.first_name} {stu.last_name}",
                "class_name": class_map.get(stu.class_id, "—"),
                "parent_id": parent.id if parent else None,
                "parent_name": f"{parent.first_name} {parent.last_name}" if parent else "Parent",
                "phone": norm_phone,
                "total_fee": fee_struct.amount,
                "balance": balance,
                "due_date": due_date.isoformat(),
                "stage": stage,
                "message": msg_text,
            })

    return reminders


@api.route("/admin/sms/fee-reminders/preview", methods=["GET"])
@login_required
def api_admin_fee_reminders_preview():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    reminders = _get_due_fee_reminders(school_id, filter_due_only=False)
    return jsonify({
        "count": len(reminders),
        "total_outstanding": sum(r["balance"] for r in reminders),
        "reminders": reminders,
    })


@api.route("/admin/sms/fee-reminders/run", methods=["POST"])
@login_required
def api_admin_fee_reminders_run():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    sender_id = settings.sender_id if settings else "SchoolStacks"

    reminders = _get_due_fee_reminders(school_id, filter_due_only=False)
    sent_count = 0
    failed_count = 0

    for r in reminders:
        res = send_school_sms(
            school_id=school_id,
            recipient_phone=r["phone"],
            message_text=r["message"],
            message_type="fee_reminder",
            recipient_name=r["parent_name"],
            recipient_type="parent",
            sender_id=sender_id,
        )
        if res.get("success"):
            sent_count += 1
        else:
            failed_count += 1

    return jsonify({
        "message": f"Fee reminders executed: {sent_count} sent, {failed_count} failed/skipped.",
        "sent_count": sent_count,
        "failed_count": failed_count,
    })


def _analyze_absenteeism(school_id):
    today = datetime.date.today()
    thirty_days_ago = today - datetime.timedelta(days=30)
    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    school = db.session.get(School, school_id)
    school_name = school.name if school else "SchoolStacks"

    template = settings.absenteeism_template if (settings and settings.absenteeism_template) else (
        "Dear Parent/Guardian, {student_name} has {days} unexplained absences from {school_name}. Please contact the school."
    )

    students = Student.query.filter_by(school_id=school_id, status="active").all()
    class_map = {c.id: c.name for c in SchoolClass.query.filter_by(school_id=school_id).all()}
    results = []

    for stu in students:
        records = (
            Attendance.query.filter(
                Attendance.school_id == school_id,
                Attendance.student_id == stu.id,
                Attendance.date >= thirty_days_ago,
                Attendance.date <= today,
            )
            .order_by(Attendance.date.desc())
            .all()
        )

        cumulative_absent = sum(1 for r in records if r.status == "Absent")

        consecutive_absent = 0
        for r in records:
            if r.date.weekday() >= 5:  # skip weekend records if any
                continue
            if r.status == "Absent":
                consecutive_absent += 1
            elif r.status in ("Present", "Late", "Excused", "Sick"):
                break

        if consecutive_absent < 2 and cumulative_absent < 5:
            continue

        parent = None
        if stu.parent_id:
            parent = db.session.get(Parent, stu.parent_id)
        if not parent:
            psl = ParentStudent.query.filter_by(school_id=school_id, student_id=stu.id).first()
            if psl:
                parent = db.session.get(Parent, psl.parent_id)

        phone = parent.phone if parent else None
        norm_phone = None
        if phone:
            try:
                norm_phone = normalize_phone_number(phone)
            except ValueError:
                norm_phone = None

        level = "Notice"
        if consecutive_absent >= 3:
            level = "Urgent Follow-up"
        elif cumulative_absent >= 5:
            level = "Admin Intervention"

        msg_text = template.format(
            school_name=school_name,
            student_name=f"{stu.first_name} {stu.last_name}",
            days=f"{consecutive_absent} consecutive" if consecutive_absent >= 2 else f"{cumulative_absent} cumulative",
        )

        results.append({
            "student_id": stu.id,
            "student_name": f"{stu.first_name} {stu.last_name}",
            "class_id": stu.class_id,
            "class_name": class_map.get(stu.class_id, "—"),
            "parent_id": parent.id if parent else None,
            "parent_name": f"{parent.first_name} {parent.last_name}" if parent else "Parent",
            "phone": norm_phone or phone,
            "consecutive_absences": consecutive_absent,
            "cumulative_absences": cumulative_absent,
            "level": level,
            "flagged_for_intervention": cumulative_absent >= 5,
            "message": msg_text,
        })

    return results


@api.route("/admin/sms/absenteeism/preview", methods=["GET"])
@login_required
def api_admin_absenteeism_preview():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    data = _analyze_absenteeism(school_id)
    return jsonify({"count": len(data), "alerts": data})


@api.route("/admin/sms/absenteeism/run", methods=["POST"])
@login_required
def api_admin_absenteeism_run():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()
    settings = SMSSettings.query.filter_by(school_id=school_id).first()
    sender_id = settings.sender_id if settings else "SchoolStacks"

    data = _analyze_absenteeism(school_id)
    sent_count = 0
    flagged_count = 0
    seven_days_ago = utc_now() - datetime.timedelta(days=7)

    for item in data:
        if item.get("flagged_for_intervention"):
            existing_int = AbsenteeismIntervention.query.filter_by(
                school_id=school_id, student_id=item["student_id"], status="flagged"
            ).first()
            if not existing_int:
                interv = AbsenteeismIntervention(
                    school_id=school_id,
                    student_id=item["student_id"],
                    class_id=item.get("class_id"),
                    trigger_type="cumulative_5",
                    consecutive_absences=item["consecutive_absences"],
                    cumulative_absences=item["cumulative_absences"],
                    status="flagged",
                    flagged_date=datetime.date.today(),
                )
                db.session.add(interv)
                flagged_count += 1

        if item.get("phone"):
            recent = SMSMessage.query.filter(
                SMSMessage.school_id == school_id,
                SMSMessage.recipient_phone == item["phone"],
                SMSMessage.message_type == "absenteeism",
                SMSMessage.created_at >= seven_days_ago,
            ).first()
            if not recent:
                res = send_school_sms(
                    school_id=school_id,
                    recipient_phone=item["phone"],
                    message_text=item["message"],
                    message_type="absenteeism",
                    recipient_name=item["parent_name"],
                    recipient_type="parent",
                    sender_id=sender_id,
                )
                if res.get("success"):
                    sent_count += 1

    db.session.commit()
    return jsonify({
        "message": f"Absenteeism sweep complete: {sent_count} SMS alerts dispatched, {flagged_count} new intervention cases flagged.",
        "sent_count": sent_count,
        "flagged_count": flagged_count,
    })


@api.route("/admin/calls", methods=["GET", "POST"])
@login_required
def api_admin_calls():
    err = _require_role("admin", "superadmin")
    if err:
        return err
    school_id = get_current_school_id()

    if request.method == "GET":
        student_id = request.args.get("student_id", type=int)
        query = ParentCommunicationLog.query.filter_by(school_id=school_id)
        if student_id:
            query = query.filter_by(student_id=student_id)

        logs = query.order_by(ParentCommunicationLog.created_at.desc()).limit(100).all()
        students_map = {s.id: f"{s.first_name} {s.last_name}" for s in Student.query.filter_by(school_id=school_id).all()}
        parents_map = {p.id: f"{p.first_name} {p.last_name}" for p in Parent.query.filter_by(school_id=school_id).all()}

        return jsonify({
            "calls": [
                {
                    "id": c.id,
                    "student_id": c.student_id,
                    "student_name": students_map.get(c.student_id, "—"),
                    "parent_id": c.parent_id,
                    "parent_name": parents_map.get(c.parent_id, "Parent"),
                    "phone_called": c.phone_called,
                    "channel": c.channel,
                    "reason": c.reason,
                    "status": c.status,
                    "remarks": c.remarks,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in logs
            ]
        })

    data = request.get_json(silent=True) or request.form
    try:
        student_id = int(data.get("student_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Student ID is required."}), 400

    phone_called = (data.get("phone_called") or "").strip()
    outcome = (data.get("outcome") or data.get("status") or "Answered").strip()
    reason = (data.get("reason") or "Follow-up").strip()
    remarks = (data.get("remarks") or "").strip()
    parent_id = data.get("parent_id")

    log_entry = ParentCommunicationLog(
        school_id=school_id,
        student_id=student_id,
        parent_id=parent_id if parent_id else None,
        staff_id=current_user.id,
        channel="call",
        direction="outbound",
        phone_called=phone_called,
        reason=reason,
        status=outcome,
        remarks=remarks,
    )
    db.session.add(log_entry)
    db.session.commit()

    return jsonify({"message": "Call logged successfully.", "id": log_entry.id}), 201


@api.route("/cron/daily-sms-tasks", methods=["GET", "POST"])
def api_cron_daily_sms_tasks():
    expected_secret = (current_app.config.get("CRON_SECRET") or os.getenv("CRON_SECRET", "")).strip()
    if expected_secret:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
        query_key = request.args.get("key", "").strip()
        if token != expected_secret and query_key != expected_secret:
            return jsonify({"error": "Unauthorized"}), 401

    schools = School.query.all()
    results = []

    for s in schools:
        settings = SMSSettings.query.filter_by(school_id=s.id).first()
        if not settings or not settings.sms_enabled:
            continue

        fee_reminders_sent = 0
        if settings.fee_reminders_enabled:
            reminders = _get_due_fee_reminders(s.id, filter_due_only=True)
            for r in reminders:
                res = send_school_sms(
                    school_id=s.id,
                    recipient_phone=r["phone"],
                    message_text=r["message"],
                    message_type="fee_reminder",
                    recipient_name=r["parent_name"],
                    recipient_type="parent",
                    sender_id=settings.sender_id or "SchoolStacks",
                )
                if res.get("success"):
                    fee_reminders_sent += 1

        absenteeism_sent = 0
        if settings.absenteeism_alerts_enabled:
            alerts = _analyze_absenteeism(s.id)
            seven_days_ago = utc_now() - datetime.timedelta(days=7)
            for a in alerts:
                if a.get("phone"):
                    recent = SMSMessage.query.filter(
                        SMSMessage.school_id == s.id,
                        SMSMessage.recipient_phone == a["phone"],
                        SMSMessage.message_type == "absenteeism",
                        SMSMessage.created_at >= seven_days_ago,
                    ).first()
                    if not recent:
                        res = send_school_sms(
                            school_id=s.id,
                            recipient_phone=a["phone"],
                            message_text=a["message"],
                            message_type="absenteeism",
                            recipient_name=a["parent_name"],
                            recipient_type="parent",
                            sender_id=settings.sender_id or "SchoolStacks",
                        )
                        if res.get("success"):
                            absenteeism_sent += 1

        results.append({
            "school_id": s.id,
            "school_name": s.name,
            "fee_reminders_sent": fee_reminders_sent,
            "absenteeism_sent": absenteeism_sent,
        })

    return jsonify({"status": "completed", "schools_processed": len(results), "summary": results}), 200

