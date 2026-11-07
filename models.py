"""
models.py — Multi-tenant SaaS schema
Every resource table carries school_id so one database serves many schools.
"""
from datetime import datetime, timezone, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from sqlalchemy.orm import synonym


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
    currency          = db.Column(db.String(10), default="ZMW")
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

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


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

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


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
    remarks        = db.Column(db.String(255), nullable=True)
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
    status     = db.Column(db.String(20), default="draft", server_default="draft", index=True)  # draft / submitted / approved / published
    remarks    = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

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


# ══════════════════════════════════════════════════════════════════
#  CLASS TEACHER ALLOCATION & SMS COMMUNICATION LAYER
# ══════════════════════════════════════════════════════════════════

class ClassTeacherAllocation(db.Model):
    """Historical and active Class Teacher allocations per academic year."""
    __tablename__ = "class_teacher_allocations"

    id                  = db.Column(db.Integer, primary_key=True)
    school_id           = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    class_id            = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True, index=True)
    teacher_id          = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False, index=True)
    academic_year       = db.Column(db.String(50), nullable=False, index=True)
    academic_year_id    = db.Column(db.Integer, db.ForeignKey("academic_years.id"), nullable=True)
    section             = db.Column(db.String(20), nullable=True)
    status              = db.Column(db.String(20), default="active", index=True)  # active, transferred, revoked
    assigned_date       = db.Column(db.Date, default=date.today)
    ended_date          = db.Column(db.Date, nullable=True)
    previous_teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    override_reason     = db.Column(db.Text, nullable=True)
    created_at          = db.Column(db.DateTime, default=utc_now)
    updated_at          = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    school_class        = db.relationship("SchoolClass", foreign_keys=[class_id])
    teacher             = db.relationship("Teacher", foreign_keys=[teacher_id])
    previous_teacher    = db.relationship("Teacher", foreign_keys=[previous_teacher_id])
    assigned_by         = db.relationship("User", foreign_keys=[assigned_by_user_id])

    assignment_date     = synonym("assigned_date")
    created_by_id       = synonym("assigned_by_user_id")

    def __init__(self, **kwargs):
        if "is_override" in kwargs:
            kwargs.pop("is_override")
        super().__init__(**kwargs)

    @property
    def is_override(self):
        return bool(self.override_reason)


class SubstituteAllocation(db.Model):
    """Temporary substitute teacher allocation for classroom attendance."""
    __tablename__ = "substitute_allocations"

    id                    = db.Column(db.Integer, primary_key=True)
    school_id             = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    class_id            = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True, index=True)
    primary_teacher_id    = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=True)
    substitute_teacher_id = db.Column(db.Integer, db.ForeignKey("teachers.id"), nullable=False)
    start_date            = db.Column(db.Date, nullable=False)
    end_date              = db.Column(db.Date, nullable=False)
    reason                = db.Column(db.Text, nullable=False)
    authorized_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_active             = db.Column(db.Boolean, default=True)
    created_at            = db.Column(db.DateTime, default=utc_now)
    updated_at            = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    school_class          = db.relationship("SchoolClass", foreign_keys=[class_id])
    primary_teacher       = db.relationship("Teacher", foreign_keys=[primary_teacher_id])
    substitute_teacher    = db.relationship("Teacher", foreign_keys=[substitute_teacher_id])
    authorized_by         = db.relationship("User", foreign_keys=[authorized_by_user_id])

    original_teacher_id   = synonym("primary_teacher_id")
    authorized_by_id      = synonym("authorized_by_user_id")


class SMSSettings(db.Model):
    """School-level SMS and Parent Communication configuration."""
    __tablename__ = "sms_settings"

    id                                 = db.Column(db.Integer, primary_key=True)
    school_id                          = db.Column(db.Integer, db.ForeignKey("schools.id"), unique=True, nullable=False, index=True)
    is_enabled                         = db.Column(db.Boolean, default=False)
    sender_id                          = db.Column(db.String(30), nullable=True)
    fee_reminders_enabled              = db.Column(db.Boolean, default=True)
    fee_reminder_days                  = db.Column(db.String(50), default="7,0,-7")
    fee_custom_message                 = db.Column(db.Text, nullable=True)
    absenteeism_alerts_enabled         = db.Column(db.Boolean, default=True)
    absenteeism_consecutive_threshold  = db.Column(db.Integer, default=2)
    absenteeism_urgent_threshold       = db.Column(db.Integer, default=3)
    absenteeism_intervention_threshold = db.Column(db.Integer, default=5)
    absenteeism_window_days            = db.Column(db.Integer, default=30)
    absenteeism_custom_message         = db.Column(db.Text, nullable=True)
    enable_subject_attendance          = db.Column(db.Boolean, default=False)
    attendance_correction_window_hours = db.Column(db.Integer, default=24)
    provider                           = db.Column(db.String(50), default="easysendsms")
    created_at                         = db.Column(db.DateTime, default=utc_now)
    updated_at                         = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    school                             = db.relationship("School", backref=db.backref("sms_settings", uselist=False))

    sms_enabled                  = synonym("is_enabled")
    fee_reminder_template        = synonym("fee_custom_message")
    absenteeism_template         = synonym("absenteeism_custom_message")
    absenteeism_consecutive_days = synonym("absenteeism_consecutive_threshold")
    absenteeism_cumulative_days  = synonym("absenteeism_intervention_threshold")

    def __init__(self, **kwargs):
        if "sms_enabled" in kwargs:
            kwargs["is_enabled"] = kwargs.pop("sms_enabled")
        if "fee_reminder_template" in kwargs:
            kwargs["fee_custom_message"] = kwargs.pop("fee_reminder_template")
        if "fee_reminder_intervals" in kwargs:
            intervals = kwargs.pop("fee_reminder_intervals")
            kwargs["fee_reminder_days"] = ",".join(str(x) for x in intervals) if isinstance(intervals, list) else str(intervals)
        if "absenteeism_template" in kwargs:
            kwargs["absenteeism_custom_message"] = kwargs.pop("absenteeism_template")
        if "absenteeism_consecutive_days" in kwargs:
            kwargs["absenteeism_consecutive_threshold"] = kwargs.pop("absenteeism_consecutive_days")
        if "absenteeism_cumulative_days" in kwargs:
            kwargs["absenteeism_intervention_threshold"] = kwargs.pop("absenteeism_cumulative_days")
        super().__init__(**kwargs)

    @property
    def sms_enabled(self):
        return self.is_enabled

    @sms_enabled.setter
    def sms_enabled(self, val):
        self.is_enabled = val

    @property
    def fee_reminder_template(self):
        return self.fee_custom_message

    @fee_reminder_template.setter
    def fee_reminder_template(self, val):
        self.fee_custom_message = val

    @property
    def fee_reminder_intervals(self):
        if not self.fee_reminder_days:
            return [7, 0, -7]
        try:
            return [int(x.strip()) for x in self.fee_reminder_days.split(",") if x.strip()]
        except Exception:
            return [7, 0, -7]

    @fee_reminder_intervals.setter
    def fee_reminder_intervals(self, val):
        if isinstance(val, list):
            self.fee_reminder_days = ",".join(str(x) for x in val)
        else:
            self.fee_reminder_days = str(val)

    @property
    def absenteeism_template(self):
        return self.absenteeism_custom_message

    @absenteeism_template.setter
    def absenteeism_template(self, val):
        self.absenteeism_custom_message = val

    @property
    def absenteeism_consecutive_days(self):
        return self.absenteeism_consecutive_threshold

    @absenteeism_consecutive_days.setter
    def absenteeism_consecutive_days(self, val):
        self.absenteeism_consecutive_threshold = val

    @property
    def absenteeism_cumulative_days(self):
        return self.absenteeism_intervention_threshold

    @absenteeism_cumulative_days.setter
    def absenteeism_cumulative_days(self, val):
        self.absenteeism_intervention_threshold = val


class SMSMessage(db.Model):
    """Outbound SMS message ledger with delivery status and provider correlation."""
    __tablename__ = "sms_messages"

    id                  = db.Column(db.Integer, primary_key=True)
    school_id           = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    recipient_phone     = db.Column(db.String(30), nullable=False)
    recipient_name      = db.Column(db.String(100), nullable=True)
    recipient_user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    student_id          = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    message_body        = db.Column(db.Text, nullable=False)
    category            = db.Column(db.String(50), nullable=False, index=True)  # fee_reminder, absenteeism, general, test
    status              = db.Column(db.String(30), default="queued", index=True)  # queued, sent, delivered, failed, rejected
    provider_message_id = db.Column(db.String(100), nullable=True, index=True)
    cost                = db.Column(db.Float, default=0.0)
    error_message       = db.Column(db.Text, nullable=True)
    retry_count         = db.Column(db.Integer, default=0)
    sent_at             = db.Column(db.DateTime, nullable=True)
    delivered_at        = db.Column(db.DateTime, nullable=True)
    provider            = db.Column(db.String(50), default="easysendsms")
    idempotency_key     = db.Column(db.String(100), unique=True, nullable=True, index=True)
    created_at          = db.Column(db.DateTime, default=utc_now, index=True)
    updated_at          = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    school              = db.relationship("School")
    student             = db.relationship("Student")
    recipient_user      = db.relationship("User")

    message_type        = synonym("category")

    def __init__(self, **kwargs):
        if "recipient_type" in kwargs:
            kwargs.pop("recipient_type")
        super().__init__(**kwargs)

    def __getitem__(self, key):
        if key == "success":
            return self.status in ("sent", "delivered", "queued")
        if key == "error":
            return self.error_message
        if key == "dry_run":
            import os
            return os.getenv("EASYSENDSMS_DRY_RUN", os.getenv("SMS_TO_DRY_RUN", "true")).lower() in ("true", "1", "yes")
        return getattr(self, key, None)

    def get(self, key, default=None):
        try:
            val = self[key]
            return val if val is not None else default
        except Exception:
            return default


class SMSDeliveryEvent(db.Model):
    """Raw delivery event callbacks received from EasySendSMS DLR."""
    __tablename__ = "sms_delivery_events"

    id                  = db.Column(db.Integer, primary_key=True)
    sms_message_id      = db.Column(db.Integer, db.ForeignKey("sms_messages.id"), nullable=True, index=True)
    provider_message_id = db.Column(db.String(100), nullable=True, index=True)
    status              = db.Column(db.String(30), nullable=False)
    raw_payload         = db.Column(db.Text, nullable=True)
    created_at          = db.Column(db.DateTime, default=utc_now)

    def __init__(self, **kwargs):
        if "event_type" in kwargs:
            kwargs["status"] = kwargs.pop("event_type")
        if "provider_status" in kwargs:
            kwargs["status"] = kwargs.pop("provider_status")
        if "payload" in kwargs:
            import json
            kwargs["raw_payload"] = json.dumps(kwargs.pop("payload"))
        super().__init__(**kwargs)

    @property
    def event_type(self):
        return self.status


class ParentCommunicationLog(db.Model):
    """Audit log of phone calls and direct communication with guardians."""
    __tablename__ = "parent_communication_logs"

    id             = db.Column(db.Integer, primary_key=True)
    school_id      = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    student_id     = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    parent_id      = db.Column(db.Integer, db.ForeignKey("parents.id"), nullable=True)
    staff_user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel        = db.Column(db.String(20), default="phone")  # phone, in_person
    phone_number   = db.Column(db.String(30), nullable=True)
    reason         = db.Column(db.String(100), nullable=False)  # absenteeism, fees, academic, behavior, general
    outcome        = db.Column(db.String(100), nullable=False)  # spoke_with_parent, left_voicemail, no_answer, wrong_number, resolved
    follow_up_date = db.Column(db.Date, nullable=True)
    remarks        = db.Column(db.Text, nullable=True)
    created_at     = db.Column(db.DateTime, default=utc_now)

    student        = db.relationship("Student")
    parent         = db.relationship("Parent")
    staff_user     = db.relationship("User")

    phone_called   = synonym("phone_number")
    status         = synonym("outcome")
    staff_id       = synonym("staff_user_id")

    def __init__(self, **kwargs):
        if "direction" in kwargs:
            kwargs.pop("direction")
        super().__init__(**kwargs)


class AbsenteeismIntervention(db.Model):
    """Students flagged for repeated unexplained absenteeism requiring administrative action."""
    __tablename__ = "absenteeism_interventions"

    id                  = db.Column(db.Integer, primary_key=True)
    school_id           = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    student_id          = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    class_id            = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=True, index=True)
    consecutive_days    = db.Column(db.Integer, default=0)
    cumulative_days     = db.Column(db.Integer, default=0)
    threshold_level     = db.Column(db.String(50), nullable=False)  # consecutive_2, consecutive_3, cumulative_5
    status              = db.Column(db.String(30), default="open", index=True)  # open, in_review, action_taken, resolved
    flagged_date        = db.Column(db.Date, default=date.today)
    last_alert_sent_at  = db.Column(db.DateTime, nullable=True)
    action_taken        = db.Column(db.Text, nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at         = db.Column(db.DateTime, nullable=True)
    created_at          = db.Column(db.DateTime, default=utc_now)

    student             = db.relationship("Student")
    school_class        = db.relationship("SchoolClass")
    resolved_by         = db.relationship("User", foreign_keys=[resolved_by_user_id])

    trigger_type         = synonym("threshold_level")
    consecutive_absences = synonym("consecutive_days")
    cumulative_absences  = synonym("cumulative_days")


class SubjectAttendance(db.Model):
    """Optional lesson-specific attendance recorded by subject teachers."""
    __tablename__ = "subject_attendance"

    id             = db.Column(db.Integer, primary_key=True)
    school_id      = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    student_id     = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    class_id       = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    subject_id     = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    date           = db.Column(db.Date, nullable=False)
    period         = db.Column(db.String(20), nullable=True)
    status         = db.Column(db.String(20), nullable=False)  # Present, Late, Absent, Excused, Sick
    remarks        = db.Column(db.String(255), nullable=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at     = db.Column(db.DateTime, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("school_id", "student_id", "subject_id", "date", name="uq_subject_attendance"),
    )


