"""
schemas.py — Marshmallow schemas for serialising SQLAlchemy models to JSON.
Every API response goes through one of these so the mobile app
gets clean, consistent data shapes.
"""
from marshmallow import Schema, fields, validate

# ── Auth ──────────────────────────────────────────────────────────
class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True, load_only=True)
             
              
class UserSchema(Schema):
    id         = fields.Int(dump_only=True)
    username   = fields.Str()
    email      = fields.Str()
    role       = fields.Str()
    school_id  = fields.Int()
    created_at = fields.DateTime(dump_only=True)
                                           
                                            
# ── School ────────────────────────────────────────────────────────
class SchoolSchema(Schema):
    id         = fields.Int(dump_only=True)
    name       = fields.Str()
    subdomain  = fields.Str()
    plan       = fields.Str()
    is_active  = fields.Bool()
    created_at = fields.DateTime(dump_only=True)


# ── Student ───────────────────────────────────────────────────────
class StudentSchema(Schema):
        id           = fields.Int(dump_only=True)
        admission_no = fields.Str(required=True)
        first_name   = fields.Str(required=True)
        last_name    = fields.Str(required=True)
        gender       = fields.Str()
        dob          = fields.Date()
        class_id     = fields.Int()
        school_id    = fields.Int(dump_only=True)
        created_at   = fields.DateTime(dump_only=True)
        # Nested
        school_class = fields.Method("get_class")
                                                 
        def get_class(self, obj):
            if obj.school_class:
                return {"id": obj.school_class.id, "name": obj.school_class.name}
            return None


class StudentCreateSchema(Schema):
    first_name   = fields.Str(required=True)
    last_name    = fields.Str(required=True)
    admission_no = fields.Str(required=True)
    gender       = fields.Str(required=True, validate=validate.OneOf(["Male", "Female"]))
    class_id     = fields.Int(required=True)
    dob          = fields.Date(load_default=None)
                             
                              
# ── Teacher ───────────────────────────────────────────────────────
class TeacherSchema(Schema):
    id                     = fields.Int(dump_only=True)
    staff_no               = fields.Str()
    first_name             = fields.Str(required=True)
    last_name              = fields.Str(required=True)
    phone                  = fields.Str()
    subject_specialization = fields.Str()
    school_id              = fields.Int(dump_only=True)


# ── Class ─────────────────────────────────────────────────────────
class ClassSchema(Schema):
    id        = fields.Int(dump_only=True)
    name      = fields.Str(required=True)
    capacity  = fields.Int()
    school_id = fields.Int(dump_only=True)
    # computed
    student_count = fields.Method("get_count")
                                 
    def get_count(self, obj):
        return len(obj.students) if obj.students else 0
                                              
                                              
# ── Attendance ────────────────────────────────────────────────────
class AttendanceSchema(Schema):
    id         = fields.Int(dump_only=True)
    student_id = fields.Int(required=True)
    class_id   = fields.Int(required=True)
    date       = fields.Date(required=True)
    status     = fields.Str(required=True, validate=validate.OneOf(["Present", "Absent"]))
    # nested student info for display
    student    = fields.Method("get_student")
                                                                              
    def get_student(self, obj):
        if obj.student:
            return {
                    "id": obj.student.id,
                    "first_name": obj.student.first_name,
                    "last_name": obj.student.last_name,
                    "admission_no": obj.student.admission_no,
                    }
        return None
        

class AttendanceBulkSchema(Schema):
    """For marking a whole class at once."""
    class_id = fields.Int(required=True)
    date     = fields.Date(required=True)
    records  = fields.List(fields.Dict(), required=True)
    # records = [{"student_id": 1, "status": "Present"}, ...]
                         
                          
# ── Fee ───────────────────────────────────────────────────────────
class FeeStructureSchema(Schema):
    id        = fields.Int(dump_only=True)
    class_id  = fields.Int(required=True)
    term_id   = fields.Int(required=True)
    amount    = fields.Float(required=True)
    school_id = fields.Int(dump_only=True)
    # nested
    term  = fields.Method("get_term")
    klass = fields.Method("get_class")
                                                               
    def get_term(self, obj):
        return {"id": obj.term.id, "name": obj.term.name} if obj.term else None
                                                                            
    def get_class(self, obj):
        return {"id": obj.school_class.id, "name": obj.school_class.name} if obj.school_class else None
                                                                                        

class PaymentSchema(Schema):
        id             = fields.Int(dump_only=True)
        student_id     = fields.Int(required=True)
        term_id        = fields.Int(required=True)
        amount_paid    = fields.Float(required=True)
        bank_reference = fields.Str(required=True)
        payment_date   = fields.Date(required=True)
        reference      = fields.Str(dump_only=True)
        # nested
        student = fields.Method("get_student")
        term    = fields.Method("get_term")
                                             
        def get_student(self, obj):
            if obj.student:
                return {
                        "id": obj.student.id,
                        "first_name": obj.student.first_name,
                        "last_name": obj.student.last_name,
                        "admission_no": obj.student.admission_no,
                        }
            return None

        def get_term(self, obj):
            return {"id": obj.term.id, "name": obj.term.name} if obj.term else None


# ── Term / Exam ───────────────────────────────────────────────────
class TermSchema(Schema):
    id         = fields.Int(dump_only=True)
    name       = fields.Str(required=True)
    start_date = fields.Date(required=True)
    end_date   = fields.Date(required=True)
    is_active  = fields.Bool()
    school_id  = fields.Int(dump_only=True)
                             
                              
class ExamSchema(Schema):
    id        = fields.Int(dump_only=True)
    name      = fields.Str(required=True)
    term_id   = fields.Int(required=True)
    date      = fields.Date()
    school_id = fields.Int(dump_only=True)
    term      = fields.Method("get_term")
                                                           
    def get_term(self, obj):
        return {"id": obj.term.id, "name": obj.term.name} if obj.term else None
        

# ── Result ────────────────────────────────────────────────────────
class ResultSchema(Schema):
    id         = fields.Int(dump_only=True)
    student_id = fields.Int(required=True)
    subject_id = fields.Int(required=True)
    exam_id    = fields.Int(required=True)
    marks      = fields.Float(required=True, validate=validate.Range(0, 100))
    school_id  = fields.Int(dump_only=True)
    grade      = fields.Method("get_grade")
    subject    = fields.Method("get_subject")
    exam       = fields.Method("get_exam")
                                         
    def get_grade(self, obj):
        m = obj.marks
        if m >= 80: return "A"
        if m >= 70: return "B"
        if m >= 60: return "C"
        if m >= 50: return "D"
        return "F"
                                                                                              
    def get_subject(self, obj):
        return {"id": obj.subject.id, "name": obj.subject.name} if obj.subject else None
                                                                                                          
    def get_exam(self, obj):
        return {"id": obj.exam.id, "name": obj.exam.name} if obj.exam else None
        

class ResultBulkSchema(Schema):
    """Enter marks for a whole class at once."""
    class_id   = fields.Int(required=True)
    subject_id = fields.Int(required=True)
    exam_id    = fields.Int(required=True)
    records    = fields.List(fields.Dict(), required=True)
    # records = [{"student_id": 1, "marks": 75.5}, ...]
                             
                              
# ── Subject ───────────────────────────────────────────────────────
class SubjectSchema(Schema):
    id        = fields.Int(dump_only=True)
    name      = fields.Str(required=True)
    code      = fields.Str(required=True)
    school_id = fields.Int(dump_only=True)
    

# ── Notification ──────────────────────────────────────────────────
class NotificationSchema(Schema):
    id         = fields.Int(dump_only=True)
    message    = fields.Str()
    type       = fields.Str()
    is_read    = fields.Bool()
    created_at = fields.DateTime(dump_only=True)
                         
                          
# ── Announcement ──────────────────────────────────────────────────
class AnnouncementSchema(Schema):
    id          = fields.Int(dump_only=True)
    title       = fields.Str()
    message     = fields.Str()
    priority    = fields.Str()
    expiry_date = fields.Date()
    created_at  = fields.DateTime(dump_only=True)
    class_id    = fields.Int(allow_none=True)
   

# ── Dashboard summaries ───────────────────────────────────────────
class AdminDashboardSchema(Schema):
    total_students    = fields.Int()
    total_teachers    = fields.Int()
    total_classes     = fields.Int()
    fees_collected    = fields.Float()
    fees_outstanding  = fields.Float()
    present_today     = fields.Int()
    absent_today      = fields.Int()
    attendance_rate   = fields.Float()
                                     
                                      
class StudentDashboardSchema(Schema):
    student          = fields.Nested(StudentSchema)
    recent_results   = fields.List(fields.Nested(ResultSchema))
    fee_balances     = fields.List(fields.Dict())
    unread_notifs    = fields.Int()
    attendance_rate  = fields.Float()
