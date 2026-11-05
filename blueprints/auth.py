"""
blueprints/auth.py — Login, logout, password change, and shared-domain school context
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User, School, utc_now
from extensions import limiter
from utils import record_activity

auth = Blueprint("auth", __name__)


@auth.route("/portal")
@login_required
def index():
    role_redirects = {
        "superadmin": "superadmin.dashboard",
        "admin":      "admin.dashboard",
        "student":    "student.dashboard",
        "teacher":    "teacher.dashboard",
        "parent":     "parent.dashboard",
    }
    dest = role_redirects.get(current_user.role)
    if dest:
        return redirect(url_for(dest))
    return render_template("index.html")


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))

    school = getattr(g, "school", None)
    schools = School.query.filter_by(is_active=True).order_by(School.name.asc()).all()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        school_subdomain = request.form.get("school_subdomain", "").strip().lower()

        if not username or not password:
            flash("All fields are required", "danger")
            return redirect(url_for("auth.login"))

        target_school = school
        if not target_school and school_subdomain:
            target_school = School.query.filter_by(
                subdomain=school_subdomain, is_active=True
            ).first()

        user = None
        if target_school:
            user = User.query.filter_by(
                school_id=target_school.id, username=username
            ).first()

        # Platform superadmin fallback when logging in without a school selected
        if not user and username == "superadmin":
            user = User.query.filter_by(username="superadmin", role="superadmin").first()

        # Single-school convenience fallback if only one active school exists and no school was specified
        if not user and not target_school and len(schools) == 1:
            target_school = schools[0]
            user = User.query.filter_by(
                school_id=target_school.id, username=username
            ).first()

        if user and check_password_hash(user.password_hash, password):
            if user.school_id:
                user_school = School.query.filter_by(id=user.school_id, is_active=True).first()
                if not user_school:
                    record_activity(
                        "auth",
                        "login_blocked_suspended",
                        f"Blocked login attempt for '{user.username}' (school suspended).",
                        school_id=user.school_id,
                        actor_user=user,
                        status="warning",
                        commit=True,
                    )
                    flash("This school account is currently inactive.", "danger")
                    return redirect(url_for("auth.login"))
                session["selected_school_subdomain"] = user_school.subdomain

            if not user.is_verified and user.role == "admin":
                flash("Please verify your email before logging in.", "warning")
                return redirect(url_for("auth.login"))

            user.last_login_at = utc_now()
            record_activity(
                "auth",
                "admin_login" if user.role == "admin" else "user_login",
                f"{user.role.title()} '{user.username}' signed in.",
                school_id=user.school_id,
                actor_user=user,
                status="success",
                commit=True,
            )
            login_user(user)
            if getattr(user, "must_change_password", False):
                flash("Initial setup: Please change your temporary password to continue.", "warning")
                return redirect(url_for("auth.change_password"))
            role_redirects = {
                "superadmin": "superadmin.dashboard",
                "admin":      "admin.dashboard",
                "student":    "student.dashboard",
                "teacher":    "teacher.dashboard",
                "parent":     "parent.dashboard",
            }
            dest = role_redirects.get(user.role, "auth.index")
            return redirect(url_for(dest))

        flash("Invalid username, school, or password", "danger")

    return render_template("login.html", school=school, schools=schools)


@auth.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password")
        new_pw     = request.form.get("new_password")
        confirm_pw = request.form.get("confirm_password")

        if not all([current_pw, new_pw, confirm_pw]):
            flash("All fields are required", "danger")
            return redirect(url_for("auth.change_password"))

        if not check_password_hash(current_user.password_hash, current_pw):
            flash("Current password is incorrect", "danger")
            return redirect(url_for("auth.change_password"))

        if new_pw != confirm_pw:
            flash("New passwords do not match", "danger")
            return redirect(url_for("auth.change_password"))

        if len(new_pw) < 8:
            flash("Password must be at least 8 characters", "danger")
            return redirect(url_for("auth.change_password"))

        current_user.set_password(new_pw)
        current_user.must_change_password = False
        db.session.commit()
        flash("Password changed successfully", "success")
        role_redirects = {
            "superadmin": "superadmin.dashboard",
            "admin":      "admin.dashboard",
            "student":    "student.dashboard",
            "teacher":    "teacher.dashboard",
            "parent":     "parent.dashboard",
        }
        dest = role_redirects.get(current_user.role, "auth.index")
        return redirect(url_for(dest))

    return render_template("change_password.html")
