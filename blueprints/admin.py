"""
blueprints/admin.py — All school administrator routes with strict multi-tenant isolation.
"""
import os
import random
import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    current_app,
    abort,
)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from models import (
    db,
    Student,
    Teacher,
    Parent,
    ParentStudent,
    SchoolClass,
    User,
    Term,
    Exam,
    Subject,
    FeeStructure,
    Payment,
    TeacherAssignment,
    Timetable,
    Announcement,
    Notification,
    Material,
    Submission,
    Result,
    Attendance,
)
from utils import (
    admin_required,
    get_current_school_id,
    calculate_balance,
    send_notification,
    generate_unique_reference,
    allowed_file,
    check_plan_limit,
)

admin = Blueprint("admin", __name__, url_prefix="/admin")


# ── Dashboard ──────────────────────────────────────────────────────────────────
@admin.route("/dashboard")
@login_required
@admin_required
def dashboard():
    school_id = get_current_school_id()
    total_students = Student.query.filter_by(school_id=school_id).count()
    total_teachers = Teacher.query.filter_by(school_id=school_id).count()
    total_classes  = SchoolClass.query.filter_by(school_id=school_id).count()
    return render_template(
        "admin/admin_dashboard.html",
        total_students=total_students,
        total_teachers=total_teachers,
        total_classes=total_classes,
    )


# ── Student Registration ───────────────────────────────────────────────────────
@admin.route("/register-student", methods=["GET", "POST"])
@login_required
@admin_required
def register_student():
    school_id = get_current_school_id()
    classes = SchoolClass.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        if not check_plan_limit("students"):
            flash("Your school has reached its plan's student limit. Please upgrade your plan.", "warning")
            return redirect(url_for("billing.plans"))

        first_name      = request.form.get("first_name", "").strip()
        last_name       = request.form.get("last_name", "").strip()
        admission_no    = request.form.get("admission_no", "").strip()
        gender          = request.form.get("gender", "").strip()
        class_id        = request.form.get("class_id")
        parent_username = request.form.get("parent_username", "").strip()
        parent_phone    = request.form.get("parent_phone", "").strip()

        if not all([first_name, last_name, admission_no, gender, class_id]):
            flash("All fields are required", "danger")
            return redirect(url_for("admin.register_student"))

        try:
            class_id = int(class_id)
        except (ValueError, TypeError):
            flash("Invalid class selected", "danger")
            return redirect(url_for("admin.register_student"))

        school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first()
        if not school_class:
            flash("Selected class does not belong to your school", "danger")
            return redirect(url_for("admin.register_student"))

        if Student.query.filter_by(school_id=school_id, admission_no=admission_no).first():
            flash("Admission number already exists in your school", "danger")
            return redirect(url_for("admin.register_student"))

        student = Student(
            school_id=school_id,
            first_name=first_name,
            last_name=last_name,
            admission_no=admission_no,
            gender=gender,
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

        # Optional parent account creation/linking
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

            student.parent_id = parent_rec.id
            link = ParentStudent(
                school_id=school_id,
                parent_id=parent_rec.id,
                student_id=student.id,
            )
            db.session.add(link)

        db.session.commit()
        flash("Student registered successfully! (Default password: student123)", "success")
        return redirect(url_for("admin.students_list"))

    return render_template("admin/register_student.html", classes=classes)


# ── Students List ─────────────────────────────────────────────────────────────
@admin.route("/students")
@login_required
@admin_required
def students_list():
    school_id = get_current_school_id()
    students = Student.query.filter_by(school_id=school_id).all()
    return render_template("admin/students_list.html", students=students)


# ── Create Class ───────────────────────────────────────────────────────────────
@admin.route("/create-class", methods=["GET", "POST"])
@login_required
@admin_required
def create_class():
    school_id = get_current_school_id()
    classes = SchoolClass.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        capacity = request.form.get("capacity")

        if not name or not capacity:
            flash("All fields are required", "danger")
            return redirect(url_for("admin.create_class"))

        try:
            capacity = int(capacity)
            if capacity <= 0:
                flash("Capacity must be greater than 0", "danger")
                return redirect(url_for("admin.create_class"))
        except (ValueError, TypeError):
            flash("Capacity must be a valid integer", "danger")
            return redirect(url_for("admin.create_class"))

        if SchoolClass.query.filter_by(school_id=school_id, name=name).first():
            flash("Class already exists", "danger")
            return redirect(url_for("admin.create_class"))

        new_class = SchoolClass(school_id=school_id, name=name, capacity=capacity)
        db.session.add(new_class)
        db.session.commit()
        flash("Class created successfully!", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/create_class.html", classes=classes)


# ── Register Teacher ───────────────────────────────────────────────────────────
@admin.route("/register-teacher", methods=["GET", "POST"])
@login_required
@admin_required
def register_teacher():
    school_id = get_current_school_id()

    if request.method == "POST":
        if not check_plan_limit("teachers"):
            flash("Your school has reached its plan's teacher limit. Please upgrade your plan.", "warning")
            return redirect(url_for("billing.plans"))

        first_name     = request.form.get("first_name", "").strip()
        last_name      = request.form.get("last_name", "").strip()
        phone          = request.form.get("phone", "").strip()
        specialization = request.form.get("subject_specialization", "").strip()

        if not first_name or not last_name or not phone:
            flash("All fields are required", "danger")
            return redirect(url_for("admin.register_teacher"))

        if not phone.isdigit():
            flash("Phone must be numbers only", "danger")
            return redirect(url_for("admin.register_teacher"))

        staff_no = "ST" + str(random.randint(1000, 9999))
        while Teacher.query.filter_by(school_id=school_id, staff_no=staff_no).first():
            staff_no = "ST" + str(random.randint(1000, 9999))

        user = User(
            school_id=school_id,
            username=staff_no,
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
            subject_specialization=specialization or None,
            staff_no=staff_no,
        )
        db.session.add(teacher)
        db.session.commit()
        flash(f"Teacher registered! Username: {staff_no} (Default password: teacher123)", "success")
        return redirect(url_for("admin.teachers_list"))

    return render_template("admin/register_teacher.html")


# ── Teachers List ─────────────────────────────────────────────────────────────
@admin.route("/teachers")
@login_required
@admin_required
def teachers_list():
    school_id = get_current_school_id()
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    return render_template("admin/teachers_list.html", teachers=teachers)


# ── Manage Terms ───────────────────────────────────────────────────────────────
@admin.route("/manage-terms", methods=["GET", "POST"])
@login_required
@admin_required
def manage_terms():
    school_id = get_current_school_id()

    if request.method == "POST":
        if "add_term" in request.form:
            name           = request.form.get("name", "").strip()
            start_date_str = request.form.get("start_date")
            end_date_str   = request.form.get("end_date")

            if not all([name, start_date_str, end_date_str]):
                flash("All fields are required", "danger")
                return redirect(url_for("admin.manage_terms"))

            try:
                start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_date   = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                flash("Invalid date format", "danger")
                return redirect(url_for("admin.manage_terms"))

            new_term = Term(
                school_id=school_id,
                name=name,
                start_date=start_date,
                end_date=end_date,
            )
            db.session.add(new_term)
            db.session.commit()
            flash("Term added successfully!", "success")
            return redirect(url_for("admin.manage_terms"))

        elif "add_exam" in request.form:
            name    = request.form.get("name", "").strip()
            term_id = request.form.get("term_id")

            if not name or not term_id:
                flash("All fields are required", "danger")
                return redirect(url_for("admin.manage_terms"))

            try:
                term_id = int(term_id)
            except (ValueError, TypeError):
                flash("Invalid term selected", "danger")
                return redirect(url_for("admin.manage_terms"))

            term = Term.query.filter_by(id=term_id, school_id=school_id).first()
            if not term:
                flash("Selected term does not belong to your school", "danger")
                return redirect(url_for("admin.manage_terms"))

            exam = Exam(school_id=school_id, name=name, term_id=term_id)
            db.session.add(exam)
            db.session.commit()
            flash("Exam added successfully!", "success")
            return redirect(url_for("admin.manage_terms"))

    terms = Term.query.filter_by(school_id=school_id).all()
    exams = Exam.query.filter_by(school_id=school_id).all()
    return render_template("admin/manage_terms.html", terms=terms, exams=exams)


# ── Add Subject ────────────────────────────────────────────────────────────────
@admin.route("/add-subject", methods=["GET", "POST"])
@login_required
@admin_required
def add_subject():
    school_id = get_current_school_id()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip()

        if not name or not code:
            flash("All fields are required", "danger")
            return redirect(url_for("admin.add_subject"))

        if Subject.query.filter_by(school_id=school_id, code=code).first():
            flash("Subject code already exists", "danger")
            return redirect(url_for("admin.add_subject"))

        new_subject = Subject(school_id=school_id, name=name, code=code)
        db.session.add(new_subject)
        db.session.commit()
        flash("Subject added successfully!", "success")
        return redirect(url_for("admin.add_subject"))

    subjects = Subject.query.filter_by(school_id=school_id).all()
    return render_template("admin/add_subject.html", subjects=subjects)


# ── Set Fees ───────────────────────────────────────────────────────────────────
@admin.route("/set-fees", methods=["GET", "POST"])
@login_required
@admin_required
def set_fees():
    school_id = get_current_school_id()
    classes = SchoolClass.query.filter_by(school_id=school_id).all()
    terms   = Term.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        class_id = request.form.get("class_id")
        term_id  = request.form.get("term_id")
        amount   = request.form.get("amount")

        if not all([class_id, term_id, amount]):
            flash("All fields are required", "danger")
            return redirect(url_for("admin.set_fees"))

        try:
            class_id = int(class_id)
            term_id  = int(term_id)
            amount   = float(amount)
            if amount <= 0:
                raise ValueError("Non-positive fee")
        except (ValueError, TypeError):
            flash("Invalid input values", "danger")
            return redirect(url_for("admin.set_fees"))

        if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
            abort(403)
        if not Term.query.filter_by(id=term_id, school_id=school_id).first():
            abort(403)

        existing = FeeStructure.query.filter_by(
            school_id=school_id, class_id=class_id, term_id=term_id
        ).first()
        if existing:
            flash("Fees already set for this class and term", "warning")
            return redirect(url_for("admin.set_fees"))

        fee = FeeStructure(
            school_id=school_id, class_id=class_id, term_id=term_id, amount=amount
        )
        db.session.add(fee)
        db.session.commit()
        flash("Fees set successfully!", "success")

    fees_list = FeeStructure.query.filter_by(school_id=school_id).all()
    return render_template(
        "admin/set_fees.html", classes=classes, terms=terms, fees_list=fees_list
    )


# ── Pay Fees (Manual Admin Recording) ─────────────────────────────────────────
@admin.route("/pay-fees/<int:student_id>", methods=["GET", "POST"])
@login_required
@admin_required
def pay_fees(student_id):
    school_id = get_current_school_id()
    student = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()
    terms   = Term.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        term_id          = request.form.get("term_id")
        amount           = request.form.get("amount")
        bank_reference   = request.form.get("bank_reference", "").strip()
        payment_date_str = request.form.get("payment_date")

        if not all([term_id, amount, bank_reference, payment_date_str]):
            flash("All fields are required", "danger")
            return redirect(url_for("admin.pay_fees", student_id=student.id))

        try:
            term_id      = int(term_id)
            amount       = float(amount)
            if amount <= 0:
                raise ValueError("Invalid amount")
            payment_date = datetime.datetime.strptime(payment_date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            flash("Invalid input", "danger")
            return redirect(url_for("admin.pay_fees", student_id=student.id))

        term = Term.query.filter_by(id=term_id, school_id=school_id).first()
        if not term:
            abort(403)

        if Payment.query.filter_by(school_id=school_id, bank_reference=bank_reference).first():
            flash("This bank reference already exists", "danger")
            return redirect(url_for("admin.pay_fees", student_id=student.id))

        reference = generate_unique_reference(school_id)
        payment = Payment(
            school_id=school_id,
            student_id=student.id,
            term_id=term_id,
            amount_paid=amount,
            currency="ZMW",
            reference=reference,
            bank_reference=bank_reference,
            payment_method="manual",
            status="completed",
            payment_date=payment_date,
        )
        db.session.add(payment)
        db.session.commit()
        flash("Payment recorded successfully!", "success")
        return redirect(url_for("admin.receipt", payment_id=payment.id))

    return render_template("admin/pay_fees.html", student=student, terms=terms)


# ── Receipt ────────────────────────────────────────────────────────────────────
@admin.route("/receipt/<int:payment_id>")
@login_required
def receipt(payment_id):
    school_id = get_current_school_id()
    payment = Payment.query.filter_by(id=payment_id, school_id=school_id).first_or_404()

    # Receipt is only available for completed payments
    if payment.status not in ("completed", None):
        flash("Receipt is only available after payment is confirmed.", "warning")
        if payment.lipila_reference_id:
            return redirect(url_for("billing.payment_status", reference_id=payment.lipila_reference_id))
        abort(403)

    # Role-based ownership verification
    if current_user.role == "student":
        own = Student.query.filter_by(
            school_id=school_id, admission_no=current_user.username
        ).first()
        if (not own or own.id != payment.student_id) and current_user.student_id != payment.student_id:
            abort(403)
    elif current_user.role == "parent":
        parent = Parent.query.filter_by(school_id=school_id, user_id=current_user.id).first()
        if not parent or not ParentStudent.query.filter_by(
            school_id=school_id, parent_id=parent.id, student_id=payment.student_id
        ).first():
            abort(403)
    elif current_user.role not in ("admin", "superadmin"):
        abort(403)

    return render_template("admin/receipt.html", payment=payment)


# ── Create Timetable ───────────────────────────────────────────────────────────
@admin.route("/create-timetable", methods=["GET", "POST"])
@login_required
@admin_required
def create_timetable():
    school_id = get_current_school_id()
    classes  = SchoolClass.query.filter_by(school_id=school_id).all()
    subjects = Subject.query.filter_by(school_id=school_id).all()
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    if request.method == "POST":
        class_id   = request.form.get("class_id")
        subject_id = request.form.get("subject_id")
        teacher_id = request.form.get("teacher_id")
        day        = request.form.get("day")
        start_time = request.form.get("start_time")
        end_time   = request.form.get("end_time")

        if not all([class_id, subject_id, teacher_id, day, start_time, end_time]):
            flash("All fields are required", "danger")
            return redirect(url_for("admin.create_timetable"))

        try:
            class_id   = int(class_id)
            subject_id = int(subject_id)
            teacher_id = int(teacher_id)
        except (ValueError, TypeError):
            flash("Invalid selection", "danger")
            return redirect(url_for("admin.create_timetable"))

        if not SchoolClass.query.filter_by(id=class_id, school_id=school_id).first():
            abort(403)
        if not Subject.query.filter_by(id=subject_id, school_id=school_id).first():
            abort(403)
        if not Teacher.query.filter_by(id=teacher_id, school_id=school_id).first():
            abort(403)

        conflict = Timetable.query.filter(
            Timetable.school_id == school_id,
            Timetable.teacher_id == teacher_id,
            Timetable.day == day,
            Timetable.start_time < end_time,
            Timetable.end_time > start_time,
        ).first()

        if conflict:
            flash("Teacher already assigned at this time", "danger")
            return redirect(url_for("admin.create_timetable"))

        timetable = Timetable(
            school_id=school_id,
            class_id=class_id,
            subject_id=subject_id,
            teacher_id=teacher_id,
            day=day,
            start_time=start_time,
            end_time=end_time,
        )
        db.session.add(timetable)
        db.session.commit()
        flash("Timetable entry added!", "success")
        return redirect(url_for("admin.create_timetable"))

    return render_template(
        "admin/create_timetable.html",
        classes=classes,
        subjects=subjects,
        teachers=teachers,
        days=days,
    )


# ── Announcements ──────────────────────────────────────────────────────────────
@admin.route("/announcements/new", methods=["GET", "POST"])
@login_required
@admin_required
def create_announcement():
    school_id = get_current_school_id()
    classes = SchoolClass.query.filter_by(school_id=school_id).all()

    if request.method == "POST":
        title    = request.form.get("title", "").strip()
        content  = request.form.get("content", "").strip()
        class_id = request.form.get("class_id", "").strip()

        if not title or not content:
            flash("Title and content are required", "danger")
            return redirect(url_for("admin.create_announcement"))

        target_class_id = None
        if class_id:
            try:
                target_class_id = int(class_id)
            except (ValueError, TypeError):
                flash("Invalid class selection", "danger")
                return redirect(url_for("admin.create_announcement"))
            if not SchoolClass.query.filter_by(id=target_class_id, school_id=school_id).first():
                abort(403)

        announcement = Announcement(
            school_id=school_id,
            title=title,
            message=content,
            class_id=target_class_id,
            user_id=current_user.id,
        )
        db.session.add(announcement)

        student_q = Student.query.filter_by(school_id=school_id)
        if target_class_id:
            student_q = student_q.filter_by(class_id=target_class_id)
        for student in student_q.all():
            user = User.query.filter_by(
                school_id=school_id, username=student.admission_no
            ).first()
            if user:
                send_notification(user.id, school_id, f"New announcement: {title}", "announcement")

        db.session.commit()
        flash("Announcement posted successfully!", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/create_announcement.html", classes=classes)


@admin.route("/announcement/delete/<int:id>", methods=["POST", "GET"])
@login_required
@admin_required
def delete_announcement(id):
    school_id = get_current_school_id()
    announcement = Announcement.query.filter_by(id=id, school_id=school_id).first_or_404()
    db.session.delete(announcement)
    db.session.commit()
    flash("Announcement deleted", "success")
    return redirect(url_for("admin.dashboard"))


# ── Analytics ──────────────────────────────────────────────────────────────────
@admin.route("/analytics")
@login_required
@admin_required
def analytics():
    school_id = get_current_school_id()
    subjects         = Subject.query.filter_by(school_id=school_id).all()
    subject_names    = []
    subject_averages = []

    for subject in subjects:
        results = Result.query.filter_by(school_id=school_id, subject_id=subject.id).all()
        avg = (sum(r.marks for r in results) / len(results)) if results else 0
        subject_names.append(subject.name)
        subject_averages.append(round(avg, 2))

    all_results = Result.query.filter_by(school_id=school_id).all()
    pass_count  = sum(1 for r in all_results if r.marks >= 50)
    fail_count  = sum(1 for r in all_results if r.marks < 50)

    attendance = Attendance.query.filter_by(school_id=school_id).all()
    present = sum(1 for a in attendance if a.status == "Present")
    absent  = sum(1 for a in attendance if a.status == "Absent")

    return render_template(
        "admin/analytics.html",
        subject_names=subject_names,
        subject_averages=subject_averages,
        pass_count=pass_count,
        fail_count=fail_count,
        present=present,
        absent=absent,
    )


# ── Timetable View ─────────────────────────────────────────────────────────────
@admin.route("/timetable/<int:class_id>")
@login_required
def view_timetable(class_id):
    school_id = get_current_school_id()
    school_class = SchoolClass.query.filter_by(id=class_id, school_id=school_id).first_or_404()
    timetable = Timetable.query.filter_by(school_id=school_id, class_id=class_id).all()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    return render_template(
        "timetable.html",
        timetable=timetable,
        days=days,
        school_class=school_class,
    )


# ── Notifications ──────────────────────────────────────────────────────────────
@admin.route("/notifications")
@login_required
def get_notifications():
    school_id = get_current_school_id()
    notifications = (
        Notification.query.filter_by(school_id=school_id, user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("notifications.html", notifications=notifications)


@admin.route("/notifications/read/<int:id>")
@login_required
def mark_read(id):
    school_id = get_current_school_id()
    note = Notification.query.filter_by(id=id, school_id=school_id).first_or_404()
    if note.user_id != current_user.id:
        abort(403)
    note.is_read = True
    db.session.commit()
    return redirect(url_for("admin.get_notifications"))


# ── File Download (Tenant-Isolated) ────────────────────────────────────────────
@admin.route("/download/<path:filename>")
@login_required
def download_file(filename):
    school_id = get_current_school_id()
    safe_name = secure_filename(os.path.basename(filename))
    if not safe_name:
        abort(404)

    # Verify the file belongs to this school's Materials or Submissions
    mat = Material.query.filter_by(school_id=school_id, filename=safe_name).first()
    sub = Submission.query.filter_by(school_id=school_id, file_path=safe_name).first()

    if not mat and not sub:
        abort(403)

    if sub and not mat:
        # Submissions can only be downloaded by teachers/admins of the school or the submitting student
        if current_user.role == "student" and sub.student_id != current_user.student_id:
            abort(403)
        folder = current_app.config["ASSIGNMENT_UPLOAD"]
    else:
        folder = current_app.config["UPLOAD_FOLDER"]

    full_path = os.path.join(folder, safe_name)
    if not os.path.isfile(full_path):
        abort(404)

    return send_file(full_path, as_attachment=True)
