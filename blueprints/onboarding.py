"""
blueprints/onboarding.py
School self-registration, subdomain/shared-domain setup, email verification, public landing & pricing.
"""
import re
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    session,
    abort,
)
from werkzeug.security import generate_password_hash
from extensions import db
from models import School, User, utc_now
from utils import send_verification_email, verify_email_token, record_activity

onboarding = Blueprint("onboarding", __name__)

SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")

RESERVED = {
    "www", "app", "api", "admin", "superadmin", "mail", "smtp",
    "ftp", "cdn", "static", "assets", "docs", "help", "support", "billing",
}


# ── Landing / public home ─────────────────────────────────────────
@onboarding.route("/")
def landing():
    return render_template("landing.html")


@onboarding.route("/s/<subdomain>")
def select_school(subdomain):
    """
    Shared-domain school entry route (e.g. https://edumanage.web.app/s/stmarys).
    Sets the school subdomain in session and redirects to login.
    """
    school = School.query.filter_by(subdomain=subdomain.lower(), is_active=True).first()
    if not school:
        abort(404)
    session["selected_school_subdomain"] = school.subdomain
    return redirect(url_for("auth.login"))


@onboarding.route("/pricing")
def pricing():
    plans = current_app.config["PLAN_LIMITS"]
    features = current_app.config["PLAN_FEATURES"]
    prices = current_app.config["PLAN_PRICES"]
    return render_template(
        "public/pricing.html",
        plans=plans,
        features=features,
        prices=prices,
    )


# ── School Registration ───────────────────────────────────────────
@onboarding.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        school_name = request.form.get("school_name", "").strip()
        subdomain   = request.form.get("subdomain", "").strip().lower()
        email       = request.form.get("email", "").strip().lower()
        phone       = request.form.get("phone", "").strip()
        password    = request.form.get("password", "")
        confirm_pw  = request.form.get("confirm_password", "")

        errors = []
        if not all([school_name, subdomain, email, password]):
            errors.append("All fields are required.")
        if password != confirm_pw:
            errors.append("Passwords do not match.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if subdomain in RESERVED:
            errors.append(f"'{subdomain}' is a reserved name. Please choose another.")
        if not SUBDOMAIN_RE.match(subdomain):
            errors.append("Subdomain can only contain lowercase letters, numbers, and hyphens (min 3 chars).")
        if School.query.filter_by(subdomain=subdomain).first():
            errors.append("That subdomain is already taken. Please choose another.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("onboarding/register.html", form=request.form)

        school = School(
            name=school_name,
            subdomain=subdomain,
            email=email,
            phone=phone or None,
            plan="free",
            trial_ends_at=utc_now() + timedelta(days=14),
            is_active=True,
        )
        db.session.add(school)
        db.session.flush()

        # In development/test or when SMTP is not configured, auto-verify so admin can log in
        smtp_configured = bool(current_app.config.get("MAIL_USERNAME"))
        admin = User(
            school_id=school.id,
            username="admin",
            email=email,
            password_hash=generate_password_hash(password),
            role="admin",
            is_verified=not smtp_configured,
        )
        if not smtp_configured:
            school.is_email_verified = True
        db.session.add(admin)
        db.session.flush()
        record_activity(
            "onboarding",
            "school_registered",
            f"School '{school.name}' ({school.subdomain}) registered with administrator '{admin.username}'.",
            school_id=school.id,
            actor_user=admin,
            target_type="school",
            target_id=school.id,
            commit=False,
        )
        db.session.commit()

        if smtp_configured:
            try:
                send_verification_email(admin)
                flash("School registered! Check your email to verify your account.", "success")
            except Exception:
                admin.is_verified = True
                school.is_email_verified = True
                db.session.commit()
                flash("School registered! You can now sign in.", "success")
        else:
            flash("School registered! You can now sign in with username 'admin'.", "success")

        session["selected_school_subdomain"] = school.subdomain
        school_url = url_for("onboarding.select_school", subdomain=school.subdomain, _external=True)
        return render_template(
            "onboarding/registered.html",
            school=school,
            school_url=school_url,
        )

    return render_template("onboarding/register.html", form={})


# ── Email Verification ───────────────────────────────────────────
@onboarding.route("/verify/<token>")
def verify_email(token):
    email = verify_email_token(token)
    if not email:
        flash("Verification link is invalid or has expired.", "danger")
        return redirect(url_for("onboarding.register"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("onboarding.register"))

    if user.is_verified:
        flash("Email already verified. You can log in.", "info")
    else:
        user.is_verified = True
        if user.school_id:
            school = db.session.get(School, user.school_id)
            if school:
                school.is_email_verified = True
        db.session.commit()
        flash("Email verified! You can now log in.", "success")

    if user.school_id:
        school = db.session.get(School, user.school_id)
        if school:
            session["selected_school_subdomain"] = school.subdomain
    return redirect(url_for("auth.login"))


# ── Resend Verification ───────────────────────────────────────────
@onboarding.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and not user.is_verified:
            try:
                send_verification_email(user)
                flash("Verification email resent! Check your inbox.", "success")
            except Exception:
                flash("Failed to send email. Please contact support.", "danger")
        else:
            flash("Email not found or already verified.", "info")
        return redirect(url_for("onboarding.resend_verification"))

    return render_template("onboarding/resend_verification.html")
