"""
blueprints/teacher.py — All teacher routes with strict multi-tenant isolation.
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
    abort,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import (
    db,
    Student,
    SchoolClass,
    Subject,
    Teacher,
    Attendance,
    Material,
    Assignment,
    Submission,
    Result,
    Exam,
    Announcement,
    Notification,
    User,
    utc_now,
)
from utils import (
    teacher_required,
    get_current_school_id,
    calculate_grade,
    send_notification,
    allowed_file,
)

teacher = Blueprint("teacher", __name__, url_prefix="/teacher")


# ── Dashboard ──────────────────────────────────────────────────────────────────
@teacher.route("/dashboard")
@login_required
@teacher_required
def dashboard():
    school_id = get_current_school_id()
    materials     = Material.query.filter_by(school_id=school_id).count()
    announcements = Announcement.query.filter_by(school_id=school_id).count()
    assignments   = Assignment.query.filter_by(school_id=school_id).order_by(Assignment.created_at.desc()).limit(5).all()
    return render_template(
        "teacher/teacher_dashboard.html",
        materials=materials,
        announcements=announcements,
        assignments=assignments,
    )


# ── Attendance ─────────────────────────────────────────────────────────────────
@teacher.route("/attendance", methods=["GET", "POST"])
@login_required
@teacher_required
def attendance():
    school_id = get_current_school_id()
    classes = SchoolClass.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        class_id = request.form.get("class_id")
        if not class_id:
            flash("Missing field required", "danger")
            return redirect(url_for("teacher.attendance"))

        try:
            class_id = int(class_id)
        except (ValueError, TypeError):
            flash("Invalid input", "danger")
            return redirect(url_for("teacher.attendance"))

        if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
            abort(403)
        return redirect(url_for("teacher.mark_attendance", class_id=class_id))

    return render_template("teacher/select_class.html", classes=classes)


@teacher.route("/attendance/<int:class_id>", methods=["GET", "POST"])
@login_required
@teacher_required
def mark_attendance(class_id):
    school_id = get_current_school_id()
    school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()
    students = Student.query.filter_by(school_id=school_id, class_id=class_id).all()

    if request.method == "POST":
        date_str = request.form.get("date")
        if not date_str:
            flash("Date is required", "danger")
            return redirect(url_for("teacher.mark_attendance", class_id=class_id))

        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            flash("Invalid date format", "danger")
            return redirect(url_for("teacher.mark_attendance", class_id=class_id))

        for student in students:
            status = request.form.get(f"status_{student.id}")
            if not status or status not in ("Present", "Absent"):
                flash("All students must have attendance marked", "danger")
                return redirect(url_for("teacher.mark_attendance", class_id=class_id))

            existing = Attendance.query.filter_by(
                school_id=school_id, student_id=student.id, date=date_obj
            ).first()
            if existing:
                existing.status = status
            else:
                record = Attendance(
                    school_id=school_id,
                    student_id=student.id,
                    class_id=class_id,
                    date=date_obj,
                    status=status,
                )
                db.session.add(record)

        db.session.commit()
        flash("Attendance marked successfully!", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template(
        "teacher/mark_attendance.html",
        students=students,
        class_id=class_id,
        school_class=school_class,
        today=datetime.date.today(),
    )


# ── Upload Material ────────────────────────────────────────────────────────────
@teacher.route("/materials/upload", methods=["GET", "POST"])
@login_required
@teacher_required
def upload_material():
    school_id = get_current_school_id()
    classes  = SchoolClass.query.filter_by(school_id=school_id).all()
    subjects = Subject.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        class_id    = request.form.get("class_id")
        subject_id  = request.form.get("subject_id")
        file        = request.files.get("file")

        if not all([title, description, class_id, subject_id, file]):
            flash("Please fill all fields and upload a file", "danger")
            return redirect(url_for("teacher.upload_material"))

        if file.filename == "":
            flash("No file selected", "danger")
            return redirect(url_for("teacher.upload_material"))

        if not allowed_file(file.filename):
            flash("File type not allowed", "danger")
            return redirect(url_for("teacher.upload_material"))

        try:
            class_id   = int(class_id)
            subject_id = int(subject_id)
        except (ValueError, TypeError):
            flash("Invalid inputs", "danger")
            return redirect(url_for("teacher.upload_material"))

        if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
            abort(403)
        if not Subject.query.filter_by(id=subject_id, school_id=school_id).first():
            abort(403)

        filename = f"{school_id}_{int(utc_now().timestamp())}_{secure_filename(file.filename)}"
        file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
        teacher_record = Teacher.query.filter_by(
            school_id=school_id, user_id=current_user.id
        ).first()

        material = Material(
            school_id=school_id,
            title=title,
            description=description,
            filename=filename,
            teacher_id=teacher_record.id if teacher_record else None,
            class_id=class_id,
            subject_id=subject_id,
        )
        db.session.add(material)

        students = Student.query.filter_by(school_id=school_id, class_id=class_id).all()
        for student in students:
            user = User.query.filter_by(
                school_id=school_id, username=student.admission_no
            ).first()
            if user:
                send_notification(
                    user.id,
                    school_id,
                    f"New material uploaded: {title}",
                    "material",
                )

        db.session.commit()
        flash("Material uploaded successfully!", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template(
        "teacher/upload_materials.html",
        classes=classes,
        subjects=subjects,
    )


# ── Create Assignment ──────────────────────────────────────────────────────────
@teacher.route("/create-assignment", methods=["GET", "POST"])
@login_required
@teacher_required
def create_assignment():
    school_id = get_current_school_id()
    classes     = SchoolClass.query.filter_by(school_id=school_id).all()
    subjects    = Subject.query.filter_by(school_id=school_id).all()
    assignments = Assignment.query.filter_by(school_id=school_id).order_by(Assignment.created_at.desc()).all()

    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        class_id    = request.form.get("class_id")
        subject_id  = request.form.get("subject_id")
        due_date    = request.form.get("due_date")

        if not all([title, description, class_id, subject_id, due_date]):
            flash("All fields are required", "danger")
            return redirect(url_for("teacher.create_assignment"))

        try:
            class_id   = int(class_id)
            subject_id = int(subject_id)
            due_dt     = datetime.datetime.strptime(due_date, "%Y-%m-%d")
        except (ValueError, TypeError):
            flash("Invalid input or date format", "danger")
            return redirect(url_for("teacher.create_assignment"))

        if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
            abort(403)
        if not Subject.query.filter_by(id=subject_id, school_id=school_id).first():
            abort(403)

        teacher_record = Teacher.query.filter_by(
            school_id=school_id, user_id=current_user.id
        ).first()
        assignment = Assignment(
            school_id=school_id,
            title=title,
            description=description,
            class_id=class_id,
            subject_id=subject_id,
            teacher_id=teacher_record.id if teacher_record else None,
            deadline=due_dt,
        )
        db.session.add(assignment)
        db.session.commit()
        flash("Assignment created!", "success")
        return redirect(url_for("teacher.create_assignment"))

    return render_template(
        "teacher/create_assignment.html",
        classes=classes,
        subjects=subjects,
        assignments=assignments,
    )


# ── View Submissions ───────────────────────────────────────────────────────────
@teacher.route("/submissions/<int:assignment_id>")
@login_required
@teacher_required
def view_submissions(assignment_id):
    school_id = get_current_school_id()
    assignment = Assignment.query.filter_by(id=assignment_id, school_id=school_id).first_or_404()
    submissions = Submission.query.filter_by(
        school_id=school_id, assignment_id=assignment_id
    ).all()
    return render_template(
        "teacher/submissions.html",
        submissions=submissions,
        assignment=assignment,
    )


# ── Grade Submission ───────────────────────────────────────────────────────────
@teacher.route("/grade/<int:submission_id>", methods=["GET", "POST"])
@login_required
@teacher_required
def grade_submission(submission_id):
    school_id = get_current_school_id()
    submission = Submission.query.filter_by(
        id=submission_id, school_id=school_id
    ).first_or_404()

    if request.method == "POST":
        marks    = request.form.get("marks")
        feedback = request.form.get("feedback", "").strip()

        if marks is None or marks == "" or not feedback:
            flash("All fields are required", "danger")
            return redirect(url_for("teacher.grade_submission", submission_id=submission_id))

        try:
            marks_val = float(marks)
        except (ValueError, TypeError):
            flash("Invalid marks value", "danger")
            return redirect(url_for("teacher.grade_submission", submission_id=submission_id))

        submission.marks    = marks_val
        submission.feedback = feedback
        db.session.commit()

        flash("Assignment graded!", "success")
        return redirect(
            url_for("teacher.view_submissions", assignment_id=submission.assignment_id)
        )

    return render_template("teacher/grade_submission.html", submission=submission)


# ── Enter Results ──────────────────────────────────────────────────────────────
@teacher.route("/enter-results", methods=["GET", "POST"])
@login_required
@teacher_required
def enter_results():
    school_id = get_current_school_id()
    classes  = SchoolClass.query.filter_by(school_id=school_id).all()
    subjects = Subject.query.filter_by(school_id=school_id).all()
    exams    = Exam.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        class_id   = request.form.get("class_id")
        subject_id = request.form.get("subject_id")
        exam_id    = request.form.get("exam_id")

        if not all([class_id, subject_id, exam_id]):
            flash("All fields required", "danger")
            return redirect(url_for("teacher.enter_results"))

        try:
            class_id   = int(class_id)
            subject_id = int(subject_id)
            exam_id    = int(exam_id)
        except (ValueError, TypeError):
            flash("Invalid input", "danger")
            return redirect(url_for("teacher.enter_results"))

        if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
            abort(403)
        if not Subject.query.filter_by(id=subject_id, school_id=school_id).first():
            abort(403)
        if not Exam.query.filter_by(id=exam_id, school_id=school_id).first():
            abort(403)

        students = Student.query.filter_by(school_id=school_id, class_id=class_id).all()
        return render_template(
            "teacher/enter_marks.html",
            students=students,
            class_id=class_id,
            subject_id=subject_id,
            exam_id=exam_id,
        )

    return render_template(
        "teacher/select_results.html",
        classes=classes,
        subjects=subjects,
        exams=exams,
    )


@teacher.route(
    "/enter-results/<int:class_id>/<int:subject_id>/<int:exam_id>",
    methods=["GET", "POST"],
)
@login_required
@teacher_required
def enter_marks(class_id, subject_id, exam_id):
    school_id = get_current_school_id()
    if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
        abort(404)
    subject = Subject.query.filter_by(id=subject_id, school_id=school_id).first_or_404()
    if not Exam.query.filter_by(id=exam_id, school_id=school_id).first():
        abort(404)

    students = Student.query.filter_by(school_id=school_id, class_id=class_id).all()

    if request.method == "POST":
        for student in students:
            marks = request.form.get(f"marks_{student.id}")
            if marks is None or marks == "":
                flash("Marks required for all students", "danger")
                return redirect(url_for("teacher.enter_results"))

            try:
                marks_val = float(marks)
            except (ValueError, TypeError):
                flash("Invalid marks entered", "danger")
                return redirect(url_for("teacher.enter_results"))

            existing = Result.query.filter_by(
                school_id=school_id,
                student_id=student.id,
                subject_id=subject_id,
                exam_id=exam_id,
            ).first()

            if existing:
                existing.marks = marks_val
            else:
                result = Result(
                    school_id=school_id,
                    student_id=student.id,
                    subject_id=subject_id,
                    exam_id=exam_id,
                    marks=marks_val,
                )
                db.session.add(result)

            user = User.query.filter_by(
                school_id=school_id, username=student.admission_no
            ).first()
            if user and subject:
                send_notification(
                    user.id,
                    school_id,
                    f"Your {subject.name} results have been uploaded",
                    "result",
                )

        db.session.commit()
        flash("Marks saved successfully", "success")
        return redirect(url_for("teacher.dashboard"))

    return render_template(
        "teacher/enter_marks.html",
        students=students,
        class_id=class_id,
        subject_id=subject_id,
        exam_id=exam_id,
    )
