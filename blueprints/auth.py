"""
blueprints/auth.py — Login, logout, password change
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User
from extensions import limiter

auth = Blueprint("auth", __name__)


@auth.route("/")
def index():
    return render_template("index.html")

# FIX: was returning raw string "Missing fields required", 404
# FIX: rate-limited to 10 login attempts per minute to block brute force
@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.index"))

    school = getattr(g, "school", None)

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # FIX: proper flash + redirect instead of raw 404 string
        if not username or not password:
            flash("All fields are required", "danger")
            return redirect(url_for("auth.login"))

        if school:
            user = User.query.filter_by(
                    school_id=school.id, username=username
                    ).first()
        else:
            user = User.query.filter_by(
                    username=username, role="superadmin"
                    ).first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_verified and user.role == "admin":
                flash("Please verify your email before logging in.", "warning")
                return redirect(url_for("auth.login"))

            login_user(user)
            role_redirects = {
                    "admin":   "admin.dashboard",
                    "student": "student.dashboard",
                    "teacher": "teacher.dashboard",
                    "parent":  "parent.dashboard",
                    }
            dest = role_redirects.get(user.role, "auth.index")
            return redirect(url_for(dest))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html", school=school)


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
            flash("Password must be at least 8 characters", "danger")                                           return redirect(url_for("auth.change_password"))

        current_user.set_password(new_pw)
        db.session.commit()
        flash("Password changed successfully", "success")
        return redirect(url_for("auth.index"))

    return render_template("change_password.html")
