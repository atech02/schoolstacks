"""
blueprints/parent.py — All parent-facing routes with strict multi-tenant & child-ownership isolation.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from models import (
    db,
    Parent,
    ParentStudent,
    Student,
    Result,
    Attendance,
    Term,
    Payment,
    Announcement,
    Notification,
)
from utils import parent_required, get_current_school_id, calculate_balance

parent = Blueprint("parent", __name__, url_prefix="/parent")


def _get_parent_and_children(school_id: int):
    p = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
    if not p:
        return None, []
    links = ParentStudent.query.filter_by(school_id=school_id, parent_id=p.id).all()
    students = [
        link.student
        for link in links
        if link.student and link.student.school_id == school_id
    ]
    return p, students


def _verify_parent_child(student_id: int, school_id: int) -> Student:
    """Ensure the requested student belongs to this school AND is linked to the current parent."""
    p = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
    if not p:
        abort(403)
    student = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()
    link = ParentStudent.query.filter_by(
        school_id=school_id, parent_id=p.id, student_id=student.id
    ).first()
    if not link:
        abort(403)
    return student


# ── Dashboard ──────────────────────────────────────────────────────────────────
@parent.route("/dashboard")
@login_required
@parent_required
def dashboard():
    school_id = get_current_school_id()
    _, students = _get_parent_and_children(school_id)
    terms = Term.query.filter_by(school_id=school_id).all()
    return render_template(
        "parent/parent_dashboard.html",
        students=students,
        terms=terms,
    )


# ── Child Results ──────────────────────────────────────────────────────────────
@parent.route("/results/<int:student_id>")
@login_required
@parent_required
def results(student_id):
    school_id = get_current_school_id()
    student = _verify_parent_child(student_id, school_id)
    results = Result.query.filter_by(school_id=school_id, student_id=student.id).all()
    return render_template("parent/results.html", results=results, student=student)


# ── Child Attendance ───────────────────────────────────────────────────────────
@parent.route("/attendance/<int:student_id>")
@login_required
@parent_required
def attendance(student_id):
    school_id = get_current_school_id()
    student = _verify_parent_child(student_id, school_id)
    records = (
        Attendance.query.filter_by(school_id=school_id, student_id=student.id)
        .order_by(Attendance.date.desc())
        .all()
    )
    return render_template("parent/attendance.html", records=records, student=student)


# ── Child Fees ─────────────────────────────────────────────────────────────────
@parent.route("/fees/<int:student_id>")
@login_required
@parent_required
def fees(student_id):
    school_id = get_current_school_id()
    student = _verify_parent_child(student_id, school_id)
    terms = Term.query.filter_by(school_id=school_id).all()
    data = []
    for term in terms:
        balance = calculate_balance(student.id, term.id, school_id)
        data.append({
            "term_id": term.id,
            "term": term.name,
            "balance": balance,
        })

    payments = (
        Payment.query.filter_by(school_id=school_id, student_id=student.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )
    return render_template(
        "parent/fees.html",
        student=student,
        data=data,
        payments=payments,
    )


# ── Announcements ──────────────────────────────────────────────────────────────
@parent.route("/announcements")
@login_required
@parent_required
def announcement():
    school_id = get_current_school_id()
    _, students = _get_parent_and_children(school_id)
    class_ids = [s.class_id for s in students if s.class_id]

    announcements = (
        Announcement.query.filter(
            Announcement.school_id == school_id,
            db.or_(
                Announcement.class_id.in_(class_ids) if class_ids else False,
                Announcement.class_id.is_(None),
            ),
        )
        .order_by(Announcement.created_at.desc())
        .all()
    )
    return render_template(
        "parent/announcements.html", announcements=announcements
    )


# ── Notifications ──────────────────────────────────────────────────────────────
@parent.route("/notifications")
@login_required
@parent_required
def notifications():
    school_id = get_current_school_id()
    notifs = (
        Notification.query.filter_by(school_id=school_id, user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("parent/notifications.html", notifications=notifs)


@parent.route("/notifications/read/<int:id>")
@login_required
@parent_required
def mark_read(id):
    school_id = get_current_school_id()
    note = Notification.query.filter_by(id=id, school_id=school_id).first_or_404()
    if note.user_id != current_user.id:
        abort(403)
    note.is_read = True
    db.session.commit()
    return redirect(url_for("parent.notifications"))
