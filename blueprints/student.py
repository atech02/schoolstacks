"""
blueprints/student.py — All student-facing routes with strict multi-tenant isolation.
"""
import os
import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    make_response,
    abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import (
    db,
    Student,
    Parent,
    ParentStudent,
    Result,
    Attendance,
    Material,
    Assignment,
    Submission,
    Announcement,
    Payment,
    Term,
    Notification,
    Timetable,
    Exam,
    Subject,
    utc_now,
)
from utils import (
    student_required,
    get_current_school_id,
    calculate_balance,
    calculate_grade,
    allowed_file,
)

student = Blueprint("student", __name__, url_prefix="/student")


def _get_current_student(school_id: int) -> Student:
    s = None
    if current_user.student_id:
        s = Student.query.filter_by(id=current_user.student_id, school_id=school_id).first()
    if not s:
        s = Student.query.filter_by(
            school_id=school_id, admission_no=current_user.username
        ).first()
    if not s:
        abort(403)
    return s


# ── Dashboard ──────────────────────────────────────────────────────────────────
@student.route("/dashboard")
@login_required
@student_required
def dashboard():
    school_id = get_current_school_id()
    s         = _get_current_student(school_id)
    results   = Result.query.filter_by(school_id=school_id, student_id=s.id).all()
    materials = Material.query.filter_by(school_id=school_id, class_id=s.class_id).all()
    terms     = Term.query.filter_by(school_id=school_id).all()
    return render_template(
        "student/student_dashboard.html",
        student=s,
        results=results,
        materials=materials,
        terms=terms,
    )


# ── Announcements ──────────────────────────────────────────────────────────────
@student.route("/announcements")
@login_required
@student_required
def announcements():
    school_id = get_current_school_id()
    s     = _get_current_student(school_id)
    today = datetime.date.today()

    page = request.args.get("page", 1, type=int)
    announcements_q = (
        Announcement.query.filter(
            Announcement.school_id == school_id,
            db.or_(
                Announcement.class_id == s.class_id,
                Announcement.class_id.is_(None),
            ),
            db.or_(
                Announcement.expiry_date.is_(None),
                Announcement.expiry_date >= today,
            ),
        )
        .order_by(Announcement.created_at.desc())
        .paginate(page=page, per_page=10)
    )
    return render_template(
        "student/announcements.html", announcements=announcements_q
    )


# ── Fees ───────────────────────────────────────────────────────────────────────
@student.route("/fees")
@login_required
@student_required
def fees():
    school_id = get_current_school_id()
    s     = _get_current_student(school_id)
    terms = Term.query.filter_by(school_id=school_id).all()
    data  = []

    for term in terms:
        balance = calculate_balance(s.id, term.id, school_id)
        data.append({
            "term_id": term.id,
            "term": term.name,
            "balance": balance,
        })

    payments = (
        Payment.query.filter_by(school_id=school_id, student_id=s.id)
        .order_by(Payment.payment_date.desc())
        .all()
    )

    return render_template(
        "student/fees.html",
        student=s,
        data=data,
        payments=payments,
    )


# ── Assignments ────────────────────────────────────────────────────────────────
@student.route("/assignments")
@login_required
@student_required
def assignments():
    school_id = get_current_school_id()
    s = _get_current_student(school_id)
    all_assignments = (
        Assignment.query.filter_by(school_id=school_id, class_id=s.class_id)
        .order_by(Assignment.created_at.desc())
        .all()
    )
    return render_template(
        "student/assignments.html",
        assignments=all_assignments,
        now=utc_now(),
    )


# ── Submit Assignment ──────────────────────────────────────────────────────────
@student.route("/submit/<int:id>", methods=["GET", "POST"])
@login_required
@student_required
def submit_assignment(id):
    school_id = get_current_school_id()
    s = _get_current_student(school_id)
    assignment = Assignment.query.filter_by(
        id=id, school_id=school_id, class_id=s.class_id
    ).first_or_404()

    if request.method == "POST":
        file = request.files.get("file")

        if not file or not file.filename:
            flash("File required", "danger")
            return redirect(url_for("student.submit_assignment", id=id))

        if not allowed_file(file.filename):
            flash("File type not allowed", "danger")
            return redirect(url_for("student.submit_assignment", id=id))

        filename = f"{school_id}_{s.id}_{int(utc_now().timestamp())}_{secure_filename(file.filename)}"
        file.save(os.path.join(current_app.config["ASSIGNMENT_UPLOAD"], filename))

        submission = Submission(
            school_id=school_id,
            assignment_id=id,
            student_id=s.id,
            file_path=filename,
        )
        db.session.add(submission)
        db.session.commit()
        flash("Assignment submitted", "success")
        return redirect(url_for("student.dashboard"))

    return render_template(
        "student/submit_assignment.html", assignment=assignment
    )


# ── Materials ──────────────────────────────────────────────────────────────────
@student.route("/materials")
@login_required
@student_required
def materials():
    school_id = get_current_school_id()
    s = _get_current_student(school_id)
    all_materials = Material.query.filter_by(
        school_id=school_id, class_id=s.class_id
    ).all()
    return render_template("student/materials.html", materials=all_materials)


# ── Report Card PDF ────────────────────────────────────────────────────────────
@student.route("/report-card/<int:student_id>/<int:term_id>")
@login_required
def report_card_pdf(student_id, term_id):
    school_id = get_current_school_id()
    s = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()
    term = Term.query.filter_by(id=term_id, school_id=school_id).first_or_404()

    # Strict ownership checks for student & parent roles
    if current_user.role == "student":
        own = _get_current_student(school_id)
        if own.id != s.id:
            abort(403)
    elif current_user.role == "parent":
        parent = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        is_linked = False
        if parent:
            if s.parent_id == parent.id:
                is_linked = True
            elif ParentStudent.query.filter_by(
                school_id=school_id, parent_id=parent.id, student_id=s.id
            ).first():
                is_linked = True
        if not is_linked:
            abort(403)
    elif current_user.role not in ("admin", "teacher", "superadmin"):
        abort(403)

    # Strictly include only approved and published results on the official report card
    results = (
        Result.query.join(Exam)
        .filter(
            Result.school_id == school_id,
            Result.student_id == s.id,
            Exam.term_id == term.id,
            (Result.status.in_(["published", "approved"]) | Result.status.is_(None)),
        )
        .all()
    )

    report      = []
    total_marks = 0.0

    for r in results:
        grade = calculate_grade(r.marks)
        report.append({
            "subject": r.subject.name if r.subject else "—",
            "marks":   r.marks,
            "grade":   grade,
        })
        total_marks += r.marks

    average     = 0.0
    final_grade = "N/A"
    if results:
        average     = total_marks / len(results)
        final_grade = calculate_grade(average)

    # Attendance statistics
    att_records = Attendance.query.filter_by(school_id=school_id, student_id=s.id).all()
    days_present = sum(1 for a in att_records if a.status in ("Present", "Late"))
    days_absent = sum(1 for a in att_records if a.status in ("Absent", "Sick", "Excused"))
    total_days = len(att_records)
    attendance_rate = round((days_present / total_days) * 100, 1) if total_days > 0 else 100.0

    # Class rank calculation based exclusively on published marks
    class_students = Student.query.filter_by(school_id=school_id, class_id=s.class_id).all()
    student_totals = {}
    for cs in class_students:
        c_res = (
            Result.query.join(Exam)
            .filter(
                Result.school_id == school_id,
                Result.student_id == cs.id,
                Exam.term_id == term.id,
                (Result.status.in_(["published", "approved"]) | Result.status.is_(None)),
            )
            .all()
        )
        student_totals[cs.id] = sum(cr.marks for cr in c_res) if c_res else 0.0

    sorted_ranks = sorted(student_totals.items(), key=lambda x: x[1], reverse=True)
    class_rank = next((idx + 1 for idx, (sid, _) in enumerate(sorted_ranks) if sid == s.id), 1)

    html = render_template(
        "student/report_card_pdf.html",
        student=s,
        school=s.school,
        term=term,
        report=report,
        total=round(total_marks, 2),
        average=round(average, 2),
        final_grade=final_grade,
        days_present=days_present,
        days_absent=days_absent,
        total_days=total_days,
        attendance_rate=attendance_rate,
        class_rank=class_rank,
        class_size=len(class_students),
        now=utc_now(),
    )

    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = make_response(pdf)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"inline; filename=report_card_{s.admission_no}.pdf"
        return response
    except Exception:
        # Fallback to printable HTML report card when GTK/WeasyPrint system libs are absent
        return make_response(html, 200)


# ── Notifications ──────────────────────────────────────────────────────────────
@student.route("/notifications")
@login_required
@student_required
def notifications():
    school_id = get_current_school_id()
    notifs = (
        Notification.query.filter_by(school_id=school_id, user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("student/notifications.html", notifications=notifs)


@student.route("/notifications/read/<int:id>")
@login_required
@student_required
def mark_read(id):
    school_id = get_current_school_id()
    note = Notification.query.filter_by(id=id, school_id=school_id).first_or_404()
    if note.user_id != current_user.id:
        abort(403)
    note.is_read = True
    db.session.commit()
    return redirect(url_for("student.notifications"))
