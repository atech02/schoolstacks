"""
api/blueprints/school_api.py
Attendance, results, fees, dashboard, notifications endpoints
"""
from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import (Attendance, Result, Payment, FeeStructure, Student,
                    SchoolClass, Subject, Exam, Term, Notification,
                    Announcement, Teacher, User)
from schemas import (AttendanceSchema, ResultSchema, PaymentSchema,
                    FeeStructureSchema, NotificationSchema,
                    AnnouncementSchema, TermSchema, ExamSchema,
                    SubjectSchema, ClassSchema, TeacherSchema)
from utils import calculate_balance, generate_unique_reference

school_api = Blueprint("school_api", __name__)

def _sid():
        return get_jwt_identity()["school_id"]
     
def _role():
        return get_jwt_identity()["role"]
         
def _uid():
        return get_jwt_identity()["user_id"]


# ══════════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════════

@school_api.route("/dashboard/admin", methods=["GET"])
@jwt_required()
def admin_dashboard():
    if _role() not in ("admin", "superadmin"):
        return jsonify({"error": "Admin required"}), 403
                 
    sid   = _sid()
    today = date.today()
                         
    total_students = Student.query.filter_by(school_id=sid).count()
    total_teachers = Teacher.query.filter_by(school_id=sid).count()
    total_classes  = SchoolClass.query.filter_by(school_id=sid).count()
                                      
    att_today = Attendance.query.filter_by(school_id=sid, date=today).all()
    present   = sum(1 for a in att_today if a.status == "Present")
    absent    = sum(1 for a in att_today if a.status == "Absent")
    att_rate  = round(present / (present + absent) * 100, 1) if (present + absent) > 0 else 0
                                                       
    # Fees
    all_payments = Payment.query.filter_by(school_id=sid).all()
    fees_collected = sum(p.amount_paid for p in all_payments)
             
    return jsonify({
        "total_students":   total_students,
        "total_teachers":   total_teachers,
        "total_classes":    total_classes,
        "present_today":    present,
        "absent_today":     absent,
        "attendance_rate":  att_rate,
        "fees_collected":   fees_collected,
        }), 200


@school_api.route("/dashboard/student", methods=["GET"])
@jwt_required()
def student_dashboard():
    sid      = _sid()
    user     = User.query.get(_uid())
    student  = Student.query.filter_by(user_id=user.id, school_id=sid).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404
                             
    results   = Result.query.filter_by(school_id=sid, student_id=student.id)\
            .order_by(Result.id.desc()).limit(5).all()
    att       = Attendance.query.filter_by(school_id=sid, student_id=student.id).all()
    total     = len(att)
    present   = sum(1 for a in att if a.status == "Present")
    att_rate  = round(present / total * 100, 1) if total > 0 else 0
                                                                                    
    unread    = Notification.query.filter_by(
            school_id=sid, user_id=user.id, is_read=False
            ).count()

    terms     = Term.query.filter_by(school_id=sid).all()
    balances  = []
    for term in terms:
        bal = calculate_balance(student.id, term.id, sid)
        balances.append({"term": term.name, "balance": bal})
                                 
    return jsonify({
        "student":         {"id": student.id, "first_name": student.first_name,
                            "last_name": student.last_name, "admission_no": student.admission_no,
                            "class_name": student.school_class.name if student.school_class else None},
        "recent_results":  ResultSchema(many=True).dump(results),
        "attendance_rate": att_rate,
        "unread_notifs":   unread,
        "fee_balances":    balances,
        }), 200


@school_api.route("/dashboard/teacher", methods=["GET"])
@jwt_required()
def teacher_dashboard():
    sid     = _sid()
    user    = User.query.get(_uid())
    teacher = Teacher.query.filter_by(user_id=user.id, school_id=sid).first()
                 
    classes = SchoolClass.query.filter_by(school_id=sid).count()
    unread  = Notification.query.filter_by(school_id=sid, user_id=user.id, is_read=False).count()
                          
    return jsonify({
        "teacher":      TeacherSchema().dump(teacher) if teacher else {},
        "total_classes":classes,
        "unread_notifs":unread,
        }), 200


# ══════════════════════════════════════════════════════════════════
#  ATTENDANCE
# ══════════════════════════════════════════════════════════════════
 
@school_api.route("/attendance", methods=["GET"])
@jwt_required()
def get_attendance():
    sid      = _sid()
    class_id = request.args.get("class_id", type=int)
    att_date = request.args.get("date")
    dt       = datetime.strptime(att_date, "%Y-%m-%d").date() if att_date else date.today()
                      
    query = Attendance.query.filter_by(school_id=sid, date=dt)
    if class_id:
        query = query.filter_by(class_id=class_id)
    
    records = query.all()
        return jsonify(AttendanceSchema(many=True).dump(records)), 200
     

@school_api.route("/attendance/bulk", methods=["POST"])
@jwt_required()
def bulk_attendance():
    if _role() not in ("teacher", "admin"):
        return jsonify({"error": "Teacher or admin required"}), 403
                 
    sid  = _sid()
    data = request.get_json(silent=True) or {}
                         
    class_id = data.get("class_id")
    att_date = data.get("date")
    records  = data.get("records", [])
                                      
    if not class_id or not att_date or not records:
        return jsonify({"error": "class_id, date, and records are required"}), 400
                                                   
    try:
        dt = datetime.strptime(att_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    saved = 0
    for rec in records:
        student_id = rec.get("student_id")
        status     = rec.get("status")
        if not student_id or status not in ("Present", "Absent"):
            continue
                                             
        existing = Attendance.query.filter_by(
                school_id=sid, student_id=student_id, date=dt
                ).first()
                                                     
        if existing:
            existing.status = status
        else:
            att = Attendance(
                    school_id=sid, student_id=student_id,
                    class_id=class_id, date=dt, status=status
                    )
            db.session.add(att)
        saved += 1

    db.session.commit()
    return jsonify({"message": f"Attendance saved for {saved} students", "date": att_date}), 200


# ══════════════════════════════════════════════════════════════════
#  RESULTS
# ══════════════════════════════════════════════════════════════════

@school_api.route("/results/bulk", methods=["POST"])
@jwt_required()
def bulk_results():
    if _role() not in ("teacher", "admin"):
        return jsonify({"error": "Teacher or admin required"}), 403
                 
    sid     = _sid()
    data    = request.get_json(silent=True) or {}
    records = data.get("records", [])
                             
    if not records:
        return jsonify({"error": "records array is required"}), 400
                                          
    saved = 0
    for rec in records:
        student_id = rec.get("student_id")
        subject_id = rec.get("subject_id")
        exam_id    = rec.get("exam_id")
        marks      = rec.get("marks")

        if not all([student_id, subject_id, exam_id, marks is not None]):
            continue
                 
        existing = Result.query.filter_by(
            school_id=sid, student_id=student_id,
            subject_id=subject_id, exam_id=exam_id
            ).first()
                         
        if existing:
            existing.marks = float(marks)
        else:
            result = Result(
                    school_id=sid, student_id=student_id,
                    subject_id=subject_id, exam_id=exam_id,
                    marks=float(marks)
                    )
            db.session.add(result)
        saved += 1
    db.session.commit()
    return jsonify({"message": f"Results saved for {saved} students"}), 200
    

# ══════════════════════════════════════════════════════════════════
#  FEES
# ══════════════════════════════════════════════════════════════════

@school_api.route("/fees/structures", methods=["GET"])
@jwt_required()
def fee_structures():
    sid = _sid()
    structures = FeeStructure.query.filter_by(school_id=sid).all()
    return jsonify(FeeStructureSchema(many=True).dump(structures)), 200
             
             
@school_api.route("/fees/pay", methods=["POST"])
@jwt_required()
def record_payment():
    if _role() not in ("admin",):
        return jsonify({"error": "Admin required"}), 403
        
    sid  = _sid()
    data = request.get_json(silent=True) or {}
         
    student_id     = data.get("student_id")
    term_id        = data.get("term_id")
    amount         = data.get("amount_paid")
    bank_reference = data.get("bank_reference")
    payment_date   = data.get("payment_date")
                              
    if not all([student_id, term_id, amount, bank_reference, payment_date]):
        return jsonify({"error": "All fields required"}), 400
                                           
    if Payment.query.filter_by(school_id=sid, bank_reference=bank_reference).first():
        return jsonify({"error": "Bank reference already exists"}), 409
                                                       
    try:
        pd = datetime.strptime(payment_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date. Use YYYY-MM-DD"}), 400
    
    reference = generate_unique_reference(sid)
     
    payment = Payment(
            school_id=sid,
            student_id=student_id,
            term_id=term_id,
            amount_paid=float(amount),
            bank_reference=bank_reference,
            payment_date=pd,
            reference=reference,
            )
    db.session.add(payment)
    db.session.commit()
                  
    return jsonify(PaymentSchema().dump(payment)), 201


@school_api.route("/fees/payments", methods=["GET"])
@jwt_required()
def list_payments():
    sid        = _sid()
    student_id = request.args.get("student_id", type=int)
    query      = Payment.query.filter_by(school_id=sid)
    if student_id:
        query = query.filter_by(student_id=student_id)
    payments = query.order_by(Payment.payment_date.desc()).all()
    return jsonify(PaymentSchema(many=True).dump(payments)), 200
                                     
                   
# ══════════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════

@school_api.route("/notifications", methods=["GET"])
@jwt_required()
def get_notifications():
    sid  = _sid()
    uid  = _uid()
    notifs = Notification.query.filter_by(school_id=sid, user_id=uid)\
            .order_by(Notification.created_at.desc()).all()
    return jsonify({
        "notifications": NotificationSchema(many=True).dump(notifs),
        "unread_count":  sum(1 for n in notifs if not n.is_read),
        }), 200


@school_api.route("/notifications/<int:notif_id>/read", methods=["PATCH"])
@jwt_required()
def mark_read(notif_id):
    sid   = _sid()
    uid   = _uid()
    notif = Notification.query.filter_by(id=notif_id, school_id=sid, user_id=uid).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({"message": "Marked as read"}), 200
    

@school_api.route("/notifications/read-all", methods=["PATCH"])
@jwt_required()
def mark_all_read():
    sid = _sid()
    uid = _uid()
    Notification.query.filter_by(school_id=sid, user_id=uid, is_read=False)\
            .update({"is_read": True})
    db.session.commit()
    return jsonify({"message": "All notifications marked as read"}), 200
                                                   
    
# ══════════════════════════════════════════════════════════════════
#  ANNOUNCEMENTS
# ══════════════════════════════════════════════════════════════════
 
@school_api.route("/announcements", methods=["GET"])
@jwt_required()
def get_announcements():
    sid   = _sid()
    today = date.today()
              
    announcements = Announcement.query.filter(
            Announcement.school_id == sid,
            db.or_(
                Announcement.expiry_date == None,
                Announcement.expiry_date >= today
                )
            ).order_by(Announcement.created_at.desc()).all()
                   
    return jsonify(AnnouncementSchema(many=True).dump(announcements)), 200
    

# ══════════════════════════════════════════════════════════════════
#  CLASSES / SUBJECTS / TERMS / EXAMS
# ══════════════════════════════════════════════════════════════════

@school_api.route("/classes", methods=["GET"])
@jwt_required()
def get_classes():
    sid     = _sid()
    classes = SchoolClass.query.filter_by(school_id=sid).all()
    return jsonify(ClassSchema(many=True).dump(classes)), 200
             
             
@school_api.route("/subjects", methods=["GET"])
@jwt_required()
def get_subjects():
    sid      = _sid()
    subjects = Subject.query.filter_by(school_id=sid).all()
    return jsonify(SubjectSchema(many=True).dump(subjects)), 200
    

@school_api.route("/terms", methods=["GET"])
@jwt_required()
def get_terms():
    sid   = _sid()
    terms = Term.query.filter_by(school_id=sid).order_by(Term.start_date.desc()).all()
    return jsonify(TermSchema(many=True).dump(terms)), 200
             
             
@school_api.route("/exams", methods=["GET"])
@jwt_required()
def get_exams():
    sid   = _sid()
    exams = Exam.query.filter_by(school_id=sid).all()
    return jsonify(ExamSchema(many=True).dump(exams)), 200
    

@school_api.route("/teachers", methods=["GET"])
@jwt_required()
def get_teachers():
    sid      = _sid()
    teachers = Teacher.query.filter_by(school_id=sid).all()
    return jsonify(TeacherSchema(many=True).dump(teachers)), 200
    


# ══════════════════════════════════════════════════════════════════
#  ANALYTICS (admin only)
# ══════════════════════════════════════════════════════════════════

@school_api.route("/analytics", methods=["GET"])
@jwt_required()
def analytics():
    if _role() not in ("admin", "superadmin"):
        return jsonify({"error": "Admin required"}), 403
                 
    sid      = _sid()
    subjects = Subject.query.filter_by(school_id=sid).all()
                         
    subject_data = []
    for subj in subjects:
        results = Result.query.filter_by(school_id=sid, subject_id=subj.id).all()
        avg     = sum(r.marks for r in results) / len(results) if results else 0
        subject_data.append({"subject": subj.name, "average": round(avg, 2), "count": len(results)})
                                                              
    all_results = Result.query.filter_by(school_id=sid).all()
    pass_count  = sum(1 for r in all_results if r.marks >= 50)
    fail_count  = len(all_results) - pass_count
    
    att         = Attendance.query.filter_by(school_id=sid).all()
    present     = sum(1 for a in att if a.status == "Present")
    absent      = len(att) - present
             
    return jsonify({
        "subject_averages": subject_data,
        "pass_count":  pass_count,
        "fail_count":  fail_count,
        "present":     present,
        "absent":      absent,
        }), 200
                  
