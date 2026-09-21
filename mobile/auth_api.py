"""
api/blueprints/auth.py — JWT auth endpoints for the mobile app
POST /api/auth/login     → access_token + refresh_token
POST /api/auth/refresh   → new access_token
POST /api/auth/logout    → blacklist token (optional)
GET  /api/auth/me        → current user info
"""
from flask import Blueprint, request, jsonify, g
from flask_jwt_extended import (
        create_access_token, create_refresh_token,
        jwt_required, get_jwt_identity, get_jwt
        )
from extensions import limiter
from models import User, Student, Teacher, Parent, School
 
api_auth = Blueprint("api_auth", __name__)
  
# In-memory token blocklist (use Redis in production)
BLOCKLIST = set()

@api_auth.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    subdomain= data.get("subdomain", "").strip().lower()
                     
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
                                  
    # Find the school by subdomain
    school = School.query.filter_by(subdomain=subdomain, is_active=True).first()
    if not school:
        return jsonify({"error": "School not found"}), 404
                                                      
    # Find user scoped to this school
    user = User.query.filter_by(school_id=school.id, username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_verified and user.role == "admin":
        return jsonify({"error": "Please verify your email first"}), 403
             
    # Build JWT identity payload
    identity = {
            "user_id":   user.id,
            "school_id": user.school_id,
            "role":      user.role,
            "username":  user.username,
            }

    access_token  = create_access_token(identity=identity)
    refresh_token = create_refresh_token(identity=identity)

    # Build profile based on role
    profile = _get_profile(user)

    return jsonify({
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "user": {
            "id":       user.id,
            "username": user.username,
            "role":     user.role,
            "email":    user.email,
            "school":   {"id": school.id, "name": school.name, "subdomain": school.subdomain},
            "profile":  profile,
                                                                                                                     }
        }), 200


@api_auth.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    identity      = get_jwt_identity()
    access_token  = create_access_token(identity=identity)
    return jsonify({"access_token": access_token}), 200
                 
                 
@api_auth.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    BLOCKLIST.add(jti)
    return jsonify({"message": "Logged out successfully"}), 200


@api_auth.route("/me", methods=["GET"])
@jwt_required()
def me():
    identity = get_jwt_identity()
    user     = User.query.get(identity["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404
                             
    school  = School.query.get(user.school_id)
    profile = _get_profile(user)
                                     
    return jsonify({
        "id":       user.id,
        "username": user.username,
        "role":     user.role,
        "email":    user.email,
        "school":   {"id": school.id, "name": school.name} if school else None,
        "profile":  profile,
        }), 200


@api_auth.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    identity   = get_jwt_identity()
    user       = User.query.get(identity["user_id"])
    data       = request.get_json(silent=True) or {}
    current_pw = data.get("current_password", "")
    new_pw     = data.get("new_password", "")
                                 
    if not user.check_password(current_pw):
        return jsonify({"error": "Current password is incorrect"}), 400
                                              
    if len(new_pw) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400
                                                          
    from extensions import db
    user.set_password(new_pw)
    db.session.commit()
    return jsonify({"message": "Password changed successfully"}), 200


def _get_profile(user):
    """Return role-specific profile fields."""
    if user.role == "student":
        s = Student.query.filter_by(user_id=user.id).first()
        if s:
            return {
                    "student_id":  s.id,
                    "first_name":  s.first_name,
                    "last_name":   s.last_name,
                    "admission_no":s.admission_no,
                    "class_id":    s.class_id,
                    "class_name":  s.school_class.name if s.school_class else None,
                    }
    elif user.role == "teacher":
        t = Teacher.query.filter_by(user_id=user.id).first()
        if t:
            return {
                    "teacher_id": t.id,
                    "first_name": t.first_name,
                    "last_name":  t.last_name,
                    "staff_no":   t.staff_no,
                    }
    elif user.role == "parent":
        p = Parent.query.filter_by(user_id=user.id).first()
        if p:
            return {
                    "parent_id": p.id,
                    "first_name":p.first_name,
                    "last_name": p.last_name,
                    }
    return {}
                                                                                         
