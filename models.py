"""
models.py — Multi-tenant SaaS schema
Every resource table carries school_id so one database serves many schools.
"""
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


def utc_now():
    """Return timezone-naive UTC datetime for SQLite compatibility without Python 3.12 deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ══════════════════════════════════════════════════════════════════
#  SAAS LAYER
# ══════════════════════════════════════════════════════════════════

class School(db.Model):
    """One row = one paying/trialling customer (a school)."""
    __tablename__ = "schools"

    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(150), nullable=False)
    subdomain = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email     = db.Column(db.String(150), nullable=False)
    phone     = db.Column(db.String(30))
    address   = db.Column(db.Text)
    logo_url  = db.Column(db.String(300))

    # Billing (Lipila + preserved historical Stripe columns)
    plan                    = db.Column(db.String(20), default="free")     # free/starter/growth/enterprise
    stripe_customer_id      = db.Column(db.String(100))                    # legacy preserved
    stripe_subscription_id  = db.Column(db.String(100))                    # legacy preserved
    lipila_customer_ref     = db.Column(db.String(100), index=True)
    lipila_subscription_ref = db.Column(db.String(100), index=True)
    billing_cycle           = db.Column(db.String(10), default="monthly")  # monthly/yearly
    trial_ends_at           = db.Column(db.DateTime)
    subscription_ends_at    = db.Column(db.DateTime)

    # Status & Activity Tracking
    is_active         = db.Column(db.Boolean, default=True)
    is_email_verified = db.Column(db.Boolean, default=False)
    created_at        = db.Column(db.DateTime, default=utc_now)
    last_activity_at  = db.Column(db.DateTime, index=True)
    suspended_at      = db.Column(db.DateTime)
    suspension_reason = db.Column(db.Text)

    def get_url(self, protocol="https", base_domain="yoursaas.com"):
        if (
            base_domain in ("localhost", "127.0.0.1")
            or base_domain.endswith(".web.app")
            or base_domain.endswith(".firebaseapp.com")
            or base_domain.endswith(".vercel.app")
        ):
            return f"{protocol}://{base_domain}/s/{self.subdomain}"
        return f"{protocol}://{self.subdomain}.{base_domain}"

    def is_on_trial(self):
        return bool(self.trial_ends_at and utc_now() < self.trial_ends_at)

    def subscription_active(self):
        if self.plan == "free":
            return True
        if self.is_on_trial():
            return True
        if self.subscription_ends_at and utc_now() < self.subscription_ends_at:
            return True
        return False


class Subscription(db.Model):
    """Subscription & SaaS billing history for a school (Lipila + legacy Stripe)."""
    __tablename__ = "subscriptions"

    id                     = db.Column(db.Integer, primary_key=True)
    school_id              = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    stripe_subscription_id = db.Column(db.String(100))  # legacy preserved
    stripe_invoice_id      = db.Column(db.String(100))  # legacy preserved
    lipila_reference_id    = db.Column(db.String(100), unique=True, index=True)
    lipila_transaction_id  = db.Column(db.String(100), index=True)
    payment_method         = db.Column(db.String(30), default="mobile_money")  # mobile_money / card
    account_number         = db.Column(db.String(50))
    plan                   = db.Column(db.String(20))
    billing_cycle          = db.Column(db.String(10))
    amount                 = db.Column(db.Float)
    currency               = db.Column(db.String(10), default="ZMW")
    status                 = db.Column(db.String(30), default="pending", index=True)  # pending/active/completed/failed/canceled/past_due
    is_sandbox_simulated   = db.Column(db.Boolean, default=False)
    period_start           = db.Column(db.DateTime)
    period_end             = db.Column(db.DateTime)
    reconciled_at          = db.Column(db.DateTime)
    created_at             = db.Column(db.DateTime, default=utc_now)
    updated_at             = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    school = db.relationship("School", backref="subscriptions")


# ══════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    school_id     = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=True, index=True)  # NULL = superadmin
    username      = db.Column(db.String(50), nullable=False)
    email         = db.Column(db.String(150))
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.String(20), nullable=False)  # superadmin/admin/teacher/student/parent
    student_id    = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    is_verified   = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=utc_now)
    last_login_at = db.Column(db.DateTime, index=True)
    must_change_password = db.Column(db.Boolean, default=False)

    __table_args__ = (
        db.UniqueConstraint("school_id", "username", name="uq_school_username"),
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_superadmin(self):
        return self.role == "superadmin"

    school = db.relationship("School", backref="users", foreign_keys=[school_id])


# ══════════════════════════════════════════════════════════════════
#  SCHOOL DATA  (all carry school_id)
# ══════════════════════════════════════════════════════════════════

class SchoolClass(db.Model):
    __tablename__ = "classes"

    id               = db.Column(db.Integer, primary_key=True)
    school_id        = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    name             = db.Column(db.String(50), nullable=False)
    capacity         = db.Column(db.Integer)
    class_teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    grade_level      = db.Column(db.String(50))
    academic_year    = db.Column(db.String(50))
    is_active        = db.Column(db.Boolean, default=True)

    class_teacher = db.relationship("Teacher", foreign_keys=[class_teacher_id])
    students = db.relationship("Student", backref="school_class", cascade="all, delete", lazy=True)
    school   = db.relationship("School", backref="classes")


class Student(db.Model):
    __tablename__ = "students"

    id           = db.Column(db.Integer, primary_key=True)
    school_id    = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"))
    admission_no = db.Column(db.String(50), nullable=False)
    first_name   = db.Column(db.String(50), nullable=False)
    last_name    = db.Column(db.String(50), nullable=False)
    dob          = db.Column(db.Date)
    gender       = db.Column(db.String(10))
    phone        = db.Column(db.String(30))
    address      = db.Column(db.Text)
    status       = db.Column(db.String(30), default="active")  # active, transferred, graduated, archived
    parent_id    = db.Column(db.Integer, db.ForeignKey("parents.id"))
    class_id     = db.Column(db.Integer, db.ForeignKey("classes.id"))
    created_at   = db.Column(db.DateTime, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("school_id", "admission_no", name="uq_school_admission"),
    )

    attendance_records = db.relationship("Attendance", backref="student", lazy=True)
    results            = db.relationship("Result",     backref="student", lazy=True)
    school             = db.relationship("School",     backref="students")


class Teacher(db.Model):
    __tablename__ = "teachers"

    id                     = db.Column(db.Integer, primary_key=True)
    school_id              = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    user_id                = db.Column(db.Integer, db.ForeignKey("users.id"))
    staff_no               = db.Column(db.String(20), nullable=False)
    first_name             = db.Column(db.String(50), nullable=False)
    last_name              = db.Column(db.String(50), nullable=False)
    email                  = db.Column(db.String(150))
    subject_specialization = db.Column(db.String(100))
    phone                  = db.Column(db.String(20))
    hire_date              = db.Column(db.Date)
    is_active              = db.Column(db.Boolean, default=True)

    school = db.relationship("School", backref="teachers")


class TeacherAssignment(db.Model):
    __tablename__ = "teacher_assignments"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    class_id   = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)

    teacher      = db.relationship("Teacher")
    school_class = db.relationship("SchoolClass")
    subject      = db.relationship("Subject")


class Parent(db.Model):
    __tablename__ = "parents"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"))
    first_name = db.Column(db.String(50), nullable=False)
    last_name  = db.Column(db.String(50), nullable=False)
    phone      = db.Column(db.String(20))
    email      = db.Column(db.String(100))
    address    = db.Column(db.Text)

    school = db.relationship("School", backref="parents")
    user   = db.relationship("User")


class ParentStudent(db.Model):
    __tablename__ = "parent_students"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    parent_id  = db.Column(db.Integer, db.ForeignKey("parents.id"))
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))

    parent  = db.relationship("Parent")
    student = db.relationship("Student")


class Subject(db.Model):
    __tablename__ = "subjects"

    id          = db.Column(db.Integer, primary_key=True)
    school_id   = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    name        = db.Column(db.String(100), nullable=False)
    code        = db.Column(db.String(20))
    description = db.Column(db.Text)
    is_active   = db.Column(db.Boolean, default=True)

    school = db.relationship("School", backref="subjects")


class Grade(db.Model):
    __tablename__ = "grades"

    id        = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=True)
    grade     = db.Column(db.String(5), nullable=False)
    min_score = db.Column(db.Float, nullable=False)
    max_score = db.Column(db.Float, nullable=False)


class Attendance(db.Model):
    __tablename__ = "attendance"

    id             = db.Column(db.Integer, primary_key=True)
    school_id      = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    student_id     = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    class_id       = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    date           = db.Column(db.Date, nullable=False)
    status         = db.Column(db.String(20), nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at     = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        db.UniqueConstraint("school_id", "student_id", "date", name="uq_school_attendance"),
    )

    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id])


class FeeStructure(db.Model):
    __tablename__ = "fee_structures"

    id        = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    class_id  = db.Column(db.Integer, db.ForeignKey("classes.id"))
    term_id   = db.Column(db.Integer, db.ForeignKey("terms.id"))
    amount    = db.Column(db.Float, nullable=False)

    school_class = db.relationship("SchoolClass")
    term         = db.relationship("Term")


class Payment(db.Model):
    __tablename__ = "payments"

    id                    = db.Column(db.Integer, primary_key=True)
    school_id             = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    student_id            = db.Column(db.Integer, db.ForeignKey("students.id"), index=True)
    term_id               = db.Column(db.Integer, db.ForeignKey("terms.id"), index=True)
    amount_paid           = db.Column(db.Float, nullable=False)
    currency              = db.Column(db.String(10), default="ZMW")
    payment_date          = db.Column(db.DateTime, default=utc_now)
    reference             = db.Column(db.String(100), index=True)
    bank_reference        = db.Column(db.String(100))
    lipila_reference_id   = db.Column(db.String(100), unique=True, index=True)
    lipila_transaction_id = db.Column(db.String(100), index=True)
    payment_method        = db.Column(db.String(30), default="manual")  # manual / mobile_money / card
    account_number        = db.Column(db.String(50))
    narration             = db.Column(db.String(255))
    status                = db.Column(db.String(30), default="completed", index=True)  # pending / completed / failed
    is_sandbox_simulated  = db.Column(db.Boolean, default=False)
    reconciled_at         = db.Column(db.DateTime)
    updated_at            = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        db.UniqueConstraint("school_id", "reference", name="uq_school_payment_ref"),
    )

    student = db.relationship("Student")
    term    = db.relationship("Term")
    school  = db.relationship("School")


class Material(db.Model):
    __tablename__ = "materials"

    id          = db.Column(db.Integer, primary_key=True)
    school_id   = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    title       = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    filename    = db.Column(db.String(255), nullable=False)
    class_id    = db.Column(db.Integer, db.ForeignKey("classes.id"))
    subject_id  = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    teacher_id  = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    term_id     = db.Column(db.Integer, db.ForeignKey("terms.id"), nullable=True)
    is_archived = db.Column(db.Boolean, default=False)
    file_size   = db.Column(db.Integer, nullable=True)
    upload_date = db.Column(db.DateTime, default=utc_now)

    school_class = db.relationship("SchoolClass")
    subject      = db.relationship("Subject")
    teacher      = db.relationship("Teacher")
    term         = db.relationship("Term")


class Announcement(db.Model):
    __tablename__ = "announcements"

    id          = db.Column(db.Integer, primary_key=True)
    school_id   = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    title       = db.Column(db.String(200), nullable=False)
    message     = db.Column(db.Text, nullable=False)
    class_id    = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"))
    priority    = db.Column(db.String(20), default="Normal")
    expiry_date = db.Column(db.Date)
    created_at  = db.Column(db.DateTime, default=utc_now)

    school_class = db.relationship("SchoolClass")


class Assignment(db.Model):
    __tablename__ = "assignments"

    id              = db.Column(db.Integer, primary_key=True)
    school_id       = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    title           = db.Column(db.String(100), nullable=False)
    description     = db.Column(db.Text)
    teacher_id      = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    subject_id      = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    class_id        = db.Column(db.Integer, db.ForeignKey("classes.id"))
    assignment_date = db.Column(db.Date)
    deadline        = db.Column(db.DateTime)
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(255))
    attachment_type = db.Column(db.String(100))
    created_at      = db.Column(db.DateTime, default=utc_now)

    subject      = db.relationship("Subject")
    school_class = db.relationship("SchoolClass")
    teacher      = db.relationship("Teacher")


class Submission(db.Model):
    __tablename__ = "submissions"

    id            = db.Column(db.Integer, primary_key=True)
    school_id     = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"))
    student_id    = db.Column(db.Integer, db.ForeignKey("students.id"))
    file_path     = db.Column(db.String(300))
    submitted_at  = db.Column(db.DateTime, default=utc_now)
    marks         = db.Column(db.Float)
    feedback      = db.Column(db.Text)

    assignment = db.relationship("Assignment")
    student    = db.relationship("Student")


class AcademicYear(db.Model):
    __tablename__ = "academic_years"

    id        = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    year      = db.Column(db.String(20), nullable=False)


class Term(db.Model):
    __tablename__ = "terms"

    id               = db.Column(db.Integer, primary_key=True)
    school_id        = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    name             = db.Column(db.String(50), nullable=False)
    start_date       = db.Column(db.Date, nullable=False)
    end_date         = db.Column(db.Date, nullable=False)
    is_active        = db.Column(db.Boolean, default=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_years.id"))

    academic_year = db.relationship("AcademicYear")


class Exam(db.Model):
    __tablename__ = "exams"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    name       = db.Column(db.String(100), nullable=False)
    term_id    = db.Column(db.Integer, db.ForeignKey("terms.id"))
    class_id   = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)
    start_date = db.Column(db.Date)
    end_date   = db.Column(db.Date)
    date       = db.Column(db.Date)
    start_time = db.Column(db.String(10))
    end_time   = db.Column(db.String(10))
    venue      = db.Column(db.String(100))
    exam_type  = db.Column(db.String(50), default="Main")
    status     = db.Column(db.String(30), default="scheduled")  # scheduled / completed / cancelled

    term         = db.relationship("Term")
    school_class = db.relationship("SchoolClass", foreign_keys=[class_id])
    subject      = db.relationship("Subject", foreign_keys=[subject_id])


class Result(db.Model):
    __tablename__ = "results"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    exam_id    = db.Column(db.Integer, db.ForeignKey("exams.id"))
    marks      = db.Column(db.Float, nullable=False)

    subject = db.relationship("Subject")
    exam    = db.relationship("Exam")


class Timetable(db.Model):
    __tablename__ = "timetables"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    class_id   = db.Column(db.Integer, db.ForeignKey("classes.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"))
    teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"))
    term_id    = db.Column(db.Integer, db.ForeignKey("terms.id"), nullable=True)
    day        = db.Column(db.String(20))
    start_time = db.Column(db.String(10))
    end_time   = db.Column(db.String(10))
    room       = db.Column(db.String(50))
    is_active  = db.Column(db.Boolean, default=True)

    subject      = db.relationship("Subject")
    teacher      = db.relationship("Teacher")
    school_class = db.relationship("SchoolClass")
    term         = db.relationship("Term")


class Notification(db.Model):
    __tablename__ = "notifications"

    id         = db.Column(db.Integer, primary_key=True)
    school_id  = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"))
    message    = db.Column(db.Text, nullable=False)
    type       = db.Column(db.String(50))
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    user = db.relationship("User")


class ActivityLog(db.Model):
    """Structured audit and school activity trail for platform monitoring."""
    __tablename__ = "activity_logs"

    id             = db.Column(db.Integer, primary_key=True)
    school_id      = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=True, index=True)
    actor_user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    actor_username = db.Column(db.String(80))
    actor_role     = db.Column(db.String(30), index=True)
    category       = db.Column(db.String(40), nullable=False, index=True)
    event_type     = db.Column(db.String(80), nullable=False, index=True)
    status         = db.Column(db.String(30), default="success", index=True)
    description    = db.Column(db.Text, nullable=False)
    target_type    = db.Column(db.String(50))
    target_id      = db.Column(db.String(100))
    metadata_json  = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, default=utc_now, index=True)

    school = db.relationship("School", backref="activity_logs", foreign_keys=[school_id])
    actor  = db.relationship("User", foreign_keys=[actor_user_id])

