"""
api/blueprints/students_api.py
GET    /api/students              → list (admin)
POST   /api/students              → create (admin)
GET    /api/students/<id>         → single student
GET    /api/students/me           → logged-in student's own profile
GET    /api/students/<id>/results → student results
GET    /api/students/<id>/attendance → student attendance summary
"""
from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import Student, User, SchoolClass, Attendance, Result, Payment, FeeStructure, Term
from schemas import StudentSchema, StudentCreateSchema, ResultSchema, AttendanceSchema
from werkzeug.security import generate_password_hash
import random


students_api = Blueprint("students_api", __name__)
student_schema       = StudentSchema()
students_schema      = StudentSchema(many=True)
student_create_schema= StudentCreateSchema()
results_schema       = ResultSchema(many=True)


def _school_id():
    return get_jwt_identity()["school_id"]
     
def _role():
    return get_jwt_identity()["role"]
             
              
@students_api.route("/students", methods=["GET"])
@jwt_required()
def list_students():
    school_id = _school_id()
    class_id  = request.args.get("class_id", type=int)
    search    = request.args.get("search", "")
                           
    query = Student.query.filter_by(school_id=school_id)
                                
    if class_id:
        query = query.filter_by(class_id=class_id)

    if search:
        query = query.filter(
                db.or_(
                    Student.first_name.ilike(f"%{search}%"),
                    Student.last_name.ilike(f"%{search}%"),
                    Student.admission_no.ilike(f"%{search}%"),
                    )
                )
                                                                                                                  
    students = query.order_by(Student.last_name).all()
    return jsonify(students_schema.dump(students)), 200


@students_api.route("/students/me", methods=["GET"])
@jwt_required()
def my_profile():
    identity  = get_jwt_identity()
    school_id = identity["school_id"]
    user      = User.query.get(identity["user_id"])
    
    student = Student.query.filter_by(user_id=user.id, school_id=school_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    return jsonify(student_schema.dump(student)), 200


@students_api.route("/students/<int:student_id>", methods=["GET"])
@jwt_required()
def get_student(student_id):
    school_id = _school_id()
    student   = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()
    return jsonify(student_schema.dump(student)), 200
             
             
@students_api.route("/students", methods=["POST"])
@jwt_required()
def create_student():
    if _role() not in ("admin", "superadmin"):
        return jsonify({"error": "Admin access required"}), 403
                             
    school_id = _school_id()
    data      = request.get_json(silent=True) or {}
    errors    = student_create_schema.validate(data)
    if errors:
        return jsonify({"errors": errors}), 422
                                                     
    # Check admission number unique within school
    if Student.query.filter_by(school_id=school_id,
            admission_no=data["admission_no"]).first():
        return jsonify({"error": "Admission number already exists"}), 409
                 
    student = Student(
            school_id=school_id,
            first_name=data["first_name"],
            last_name=data["last_name"],
            admission_no=data["admission_no"],
            gender=data["gender"],
            class_id=data["class_id"],
            dob=data.get("dob"),
            )
    db.session.add(student)
    db.session.flush()

    # Create login user
    user = User(
            school_id=school_id,
            username=data["admission_no"],
            email=data.get("email", ""),
            password_hash=generate_password_hash("student123"),
            role="student",
            is_verified=True,
            student_id=student.id,
            )
    db.session.add(user)
    db.session.commit()
                 
    return jsonify(student_schema.dump(student)), 201


@students_api.route("/students/<int:student_id>/results", methods=["GET"])
@jwt_required()
def student_results(student_id):
    school_id = _school_id()
    identity  = get_jwt_identity()
             
    # Students can only see their own results
    if identity["role"] == "student":
        user    = User.query.get(identity["user_id"])
        student = Student.query.filter_by(user_id=user.id, school_id=school_id).first()
    
        if not student or student.id != student_id:
            return jsonify({"error": "Unauthorized"}), 403
                                                              
    results = Result.query.filter_by(
            school_id=school_id, student_id=student_id
            ).all()

    # Group by exam
    grouped = {}
    for r in results:
        exam_name = r.exam.name if r.exam else "Unknown"
        if exam_name not in grouped:
            grouped[exam_name] = []
        grouped[exam_name].append(ResultSchema().dump(r))
                                                          
    return jsonify({"results": ResultSchema(many=True).dump(results), "grouped": grouped}), 200


@students_api.route("/students/<int:student_id>/attendance", methods=["GET"])
@jwt_required()
def student_attendance(student_id):
    school_id = _school_id()
    records = Attendance.query.filter_by(
            school_id=school_id, student_id=student_id
            ).order_by(Attendance.date.desc()).all()
             
    total   = len(records)
    present = sum(1 for r in records if r.status == "Present")
    absent  = total - present
    rate    = round((present / total * 100), 1) if total > 0 else 0
                             
    return jsonify({
        "total":   total,
        "present": present,
        "absent":  absent,
        "rate":    rate,
        "records": AttendanceSchema(many=True).dump(records),
        }), 200


@students_api.route("/students/<int:student_id>/fees", methods=["GET"])
@jwt_required()
def student_fees(student_id):
    school_id = _school_id()
    student   = Student.query.filter_by(id=student_id, school_id=school_id).first_or_404()
    terms     = Term.query.filter_by(school_id=school_id).all()
                 
    from utils import calculate_balance
    balances = []
    for term in terms:
        balance = calculate_balance(student_id, term.id, school_id)
        payments = Payment.query.filter_by(
                school_id=school_id, student_id=student_id, term_id=term.id
                ).all()
        fee_structure = FeeStructure.query.filter_by(
                school_id=school_id, class_id=student.class_id, term_id=term.id
                ).first()
        balances.append({
            "term":          {"id": term.id, "name": term.name},
            "fee_amount":    fee_structure.amount if fee_structure else 0,
            "total_paid":    sum(p.amount_paid for p in payments),
            "balance":       balance,
            "is_paid":       balance <= 0,
            "payment_count": len(payments),
            })

        return jsonify({"student_id": student_id, "balances": balances}), 200
          
