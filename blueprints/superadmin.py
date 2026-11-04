"""
blueprints/superadmin.py — Platform owner dashboard: see all schools, usage, revenue.
"""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required
from sqlalchemy import func
from extensions import db
from models import School, User, Student, Teacher, Subscription, Notification, utc_now
from utils import superadmin_required, record_activity

superadmin = Blueprint("superadmin", __name__, url_prefix="/superadmin")


# ── Dashboard ─────────────────────────────────────────────────────
@superadmin.route("/")
@login_required
@superadmin_required
def dashboard():
    total_schools  = School.query.count()
    active_schools = School.query.filter_by(is_active=True).count()
    total_students = Student.query.count()
    total_teachers = Teacher.query.count()

    paid_schools = School.query.filter(School.plan != "free").all()
    mrr = sum(_school_mrr(s) for s in paid_schools)

    cutoff = utc_now() - timedelta(days=30)
    recent_schools = (
        School.query.filter(School.created_at >= cutoff)
        .order_by(School.created_at.desc())
        .all()
    )

    plan_counts = (
        db.session.query(School.plan, func.count(School.id))
        .group_by(School.plan)
        .all()
    )

    recent_subs = (
        Subscription.query.order_by(Subscription.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "superadmin/dashboard.html",
        total_schools=total_schools,
        active_schools=active_schools,
        total_students=total_students,
        total_teachers=total_teachers,
        mrr=round(mrr, 2),
        recent_schools=recent_schools,
        plan_counts=dict(plan_counts),
        recent_subs=recent_subs,
    )


# ── All Schools ───────────────────────────────────────────────────
@superadmin.route("/schools")
@login_required
@superadmin_required
def schools():
    q      = request.args.get("q", "").strip()
    plan   = request.args.get("plan", "").strip()
    status = request.args.get("status", "").strip()

    query = School.query
    if q:
        query = query.filter(
            School.name.ilike(f"%{q}%") | School.subdomain.ilike(f"%{q}%")
        )
    if plan:
        query = query.filter_by(plan=plan)
    if status == "active":
        query = query.filter_by(is_active=True)
    elif status == "inactive":
        query = query.filter_by(is_active=False)

    all_schools = query.order_by(School.created_at.desc()).all()

    return render_template(
        "superadmin/schools.html",
        schools=all_schools,
        q=q,
        plan=plan,
        status=status,
    )


# ── School Detail ─────────────────────────────────────────────────
@superadmin.route("/schools/<int:school_id>")
@login_required
@superadmin_required
def school_detail(school_id):
    school   = School.query.get_or_404(school_id)
    students = Student.query.filter_by(school_id=school_id).count()
    teachers = Teacher.query.filter_by(school_id=school_id).count()
    subs     = (
        Subscription.query.filter_by(school_id=school_id)
        .order_by(Subscription.created_at.desc())
        .all()
    )
    users = User.query.filter_by(school_id=school_id).all()
    return render_template(
        "superadmin/school_detail.html",
        school=school,
        students=students,
        teachers=teachers,
        subs=subs,
        users=users,
    )


# ── Activate / Deactivate School ─────────────────────────────────
@superadmin.route("/schools/<int:school_id>/toggle", methods=["POST"])
@login_required
@superadmin_required
def toggle_school(school_id):
    school = School.query.get_or_404(school_id)
    reason = (request.form.get("reason") or "Administrative status toggle").strip()
    school.is_active = not school.is_active
    now = utc_now()
    if not school.is_active:
        school.suspended_at = now
        school.suspension_reason = reason
    else:
        school.suspended_at = None
        school.suspension_reason = None
    status = "reactivated" if school.is_active else "suspended"
    record_activity(
        "school_status",
        "school_reactivated" if school.is_active else "school_suspended",
        f"School '{school.name}' {status}. Reason: {reason}",
        school_id=school.id,
        status="success" if school.is_active else "warning",
        target_type="school",
        target_id=school.id,
        metadata={"action": status, "reason": reason},
        commit=False,
    )
    db.session.commit()
    flash(f"School '{school.name}' has been {status}.", "success")
    return redirect(url_for("superadmin.school_detail", school_id=school_id))


# ── Review / Sync Plan (No Unpaid Payment Bypass) ────────────────
@superadmin.route("/schools/<int:school_id>/plan", methods=["POST"])
@login_required
@superadmin_required
def override_plan(school_id):
    school   = School.query.get_or_404(school_id)
    new_plan = (request.form.get("plan") or "").strip().lower()
    reason   = (request.form.get("reason") or "Administrative plan adjustment").strip()
    valid    = {"free", "starter", "growth", "enterprise"}
    if new_plan not in valid:
        flash("Invalid plan.", "danger")
    elif new_plan != "free":
        verified_sub = (
            Subscription.query.filter(
                Subscription.school_id == school.id,
                Subscription.plan == new_plan,
                Subscription.status.in_(["active", "completed"]),
            )
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not verified_sub:
            flash("Cannot assign paid plan without a verified Lipila subscription payment.", "danger")
            return redirect(url_for("superadmin.school_detail", school_id=school_id))
        school.plan = new_plan
        school.billing_cycle = verified_sub.billing_cycle or school.billing_cycle
        if verified_sub.period_end:
            school.subscription_ends_at = verified_sub.period_end
        record_activity(
            "subscription",
            "subscription_plan_changed",
            f"School '{school.name}' plan synced to {new_plan.title()}. Reason: {reason}",
            school_id=school.id,
            status="info",
            target_type="school",
            target_id=school.id,
            commit=False,
        )
        db.session.commit()
        flash(f"Plan synced to {new_plan.title()}.", "success")
    else:
        school.plan = "free"
        record_activity(
            "subscription",
            "subscription_plan_changed",
            f"School '{school.name}' plan downgraded to Free. Reason: {reason}",
            school_id=school.id,
            status="info",
            target_type="school",
            target_id=school.id,
            commit=False,
        )
        db.session.commit()
        flash("Plan updated to Free.", "success")
    return redirect(url_for("superadmin.school_detail", school_id=school_id))


# ── Usage Analytics ───────────────────────────────────────────────
@superadmin.route("/analytics")
@login_required
@superadmin_required
def analytics():
    months, signup_counts = _monthly_signups(12)
    _, revenue_counts = _monthly_revenue(12)

    plan_data = (
        db.session.query(School.plan, func.count(School.id))
        .group_by(School.plan)
        .all()
    )

    return render_template(
        "superadmin/analytics.html",
        months=months,
        signup_counts=signup_counts,
        revenue_counts=revenue_counts,
        plan_data=dict(plan_data),
    )


# ── API: Stats JSON (for live dashboard refresh) ──────────────────
@superadmin.route("/api/stats")
@login_required
@superadmin_required
def api_stats():
    return jsonify({
        "schools":  School.query.count(),
        "students": Student.query.count(),
        "teachers": Teacher.query.count(),
        "paid":     School.query.filter(School.plan != "free").count(),
    })


# ── Helpers ───────────────────────────────────────────────────────
def _school_mrr(school):
    """Estimate MRR (ZMW) from a school's plan."""
    prices = current_app.config.get("PLAN_PRICES", current_app.config["STRIPE_PRICES"])
    info = prices.get(school.plan, {})
    if school.billing_cycle == "yearly":
        return info.get("amount_yearly", 0) / 12
    return info.get("amount_monthly", 0)


def _monthly_signups(n_months):
    months, counts = [], []
    now = utc_now()
    for i in range(n_months - 1, -1, -1):
        start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        end   = (start + timedelta(days=32)).replace(day=1)
        c     = School.query.filter(
            School.created_at >= start,
            School.created_at < end,
        ).count()
        months.append(start.strftime("%b %Y"))
        counts.append(c)
    return months, counts


def _monthly_revenue(n_months):
    months, amounts = [], []
    now = utc_now()
    for i in range(n_months - 1, -1, -1):
        start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        end   = (start + timedelta(days=32)).replace(day=1)
        total = (
            db.session.query(func.sum(Subscription.amount))
            .filter(
                Subscription.created_at >= start,
                Subscription.created_at < end,
                Subscription.status.in_(["active", "completed"]),
                Subscription.is_sandbox_simulated == False,  # noqa: E712
            )
            .scalar()
            or 0
        )
        months.append(start.strftime("%b %Y"))
        amounts.append(round(total, 2))
    return months, amounts
