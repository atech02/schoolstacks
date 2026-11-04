"""
blueprints/billing.py
Lipila payment integration for:
  A. School SaaS Subscriptions (Starter, Growth, Enterprise in ZMW)
  B. Parent & Student School Fee Collections (Mobile Money & Hosted Card in ZMW)
Includes webhook verification, status reconciliation, idempotency, and a
development-only Sandbox Simulator.
"""
import logging
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    g,
    jsonify,
    abort,
)
from flask_login import login_required, current_user
from extensions import db, csrf
from models import School, Subscription, Student, Term, Payment, Parent, ParentStudent, User, utc_now
from utils import (
    admin_required,
    get_current_school_id,
    calculate_balance,
    generate_unique_reference,
    send_notification,
)
from services.lipila import LipilaClient, LipilaError, normalize_zambia_phone

logger = logging.getLogger(__name__)

billing = Blueprint("billing", __name__, url_prefix="/billing")


def _get_current_school_or_403():
    school_id = get_current_school_id(required=True)
    school = School.query.filter_by(id=school_id, is_active=True).first()
    if not school:
        abort(403)
    return school


def _authorize_student_fee_access(student_id: int) -> tuple[Student, School]:
    """
    Verify that current_user is authorized to view/pay fees for student_id
    within their own school. Never trusts client school_id.
    """
    school_id = get_current_school_id(required=True)
    school = School.query.filter_by(id=school_id, is_active=True).first()
    if not school:
        abort(403)

    student = Student.query.filter_by(id=student_id, school_id=school.id).first()
    if not student:
        abort(404)

    if current_user.role == "student":
        own = Student.query.filter_by(
            school_id=school.id, admission_no=current_user.username
        ).first()
        if (not own or own.id != student.id) and current_user.student_id != student.id:
            abort(403)
    elif current_user.role == "parent":
        parent = Parent.query.filter_by(
            school_id=school.id, user_id=current_user.id
        ).first()
        if not parent:
            abort(403)
        link = ParentStudent.query.filter_by(
            school_id=school.id, parent_id=parent.id, student_id=student.id
        ).first()
        if not link:
            abort(403)
    elif current_user.role == "admin":
        if current_user.school_id != school.id:
            abort(403)
    else:
        abort(403)

    return student, school


def _settle_subscription(sub: Subscription, new_status: str, transaction_id: str = None, is_simulated: bool = False):
    """
    Idempotently transition a Subscription record to completed/active or failed.
    Only activates the school's plan on verified completion.
    """
    if sub.status in ("active", "completed"):
        return sub

    now = utc_now()
    sub.reconciled_at = now
    if transaction_id:
        sub.lipila_transaction_id = transaction_id
    if is_simulated:
        sub.is_sandbox_simulated = True

    if new_status == "completed":
        days = 365 if sub.billing_cycle == "yearly" else 30
        sub.status = "active"
        sub.period_start = now
        sub.period_end = now + timedelta(days=days)

        school = db.session.get(School, sub.school_id)
        if school:
            school.plan = sub.plan
            school.billing_cycle = sub.billing_cycle
            school.lipila_subscription_ref = sub.lipila_reference_id
            school.subscription_ends_at = sub.period_end
        from utils import record_activity
        record_activity(
            "subscription",
            "subscription_confirmed",
            f"Subscription payment confirmed for {sub.plan.title()} ({sub.billing_cycle}) — K{float(sub.amount or 0):.2f} ({sub.lipila_reference_id}).",
            school_id=sub.school_id,
            status="success",
            target_type="subscription",
            target_id=sub.lipila_reference_id,
            commit=False,
        )
        db.session.commit()
        logger.info("Subscription activated ref=%s school_id=%s plan=%s", sub.lipila_reference_id, sub.school_id, sub.plan)
    elif new_status == "failed":
        sub.status = "failed"
        from utils import record_activity
        record_activity(
            "subscription",
            "subscription_failed",
            f"Subscription payment failed for {sub.plan.title()} ({sub.billing_cycle}) — K{float(sub.amount or 0):.2f} ({sub.lipila_reference_id}).",
            school_id=sub.school_id,
            status="failed",
            target_type="subscription",
            target_id=sub.lipila_reference_id,
            commit=False,
        )
        db.session.commit()
        logger.info("Subscription payment failed ref=%s school_id=%s", sub.lipila_reference_id, sub.school_id)

    return sub


def _settle_fee_payment(payment: Payment, new_status: str, transaction_id: str = None, is_simulated: bool = False):
    """
    Idempotently transition a student Fee Payment record to completed or failed.
    Generates unique receipt reference (RCT-xxxxx) ONLY upon verified completion.
    """
    if payment.status == "completed":
        return payment

    now = utc_now()
    payment.reconciled_at = now
    if transaction_id:
        payment.lipila_transaction_id = transaction_id
    if is_simulated:
        payment.is_sandbox_simulated = True

    if new_status == "completed":
        payment.status = "completed"
        payment.payment_date = now
        if not payment.reference:
            payment.reference = generate_unique_reference(payment.school_id)
        if not payment.bank_reference:
            payment.bank_reference = transaction_id or payment.lipila_reference_id

        # Notify student user if account exists
        student = Student.query.filter_by(id=payment.student_id, school_id=payment.school_id).first()
        if student:
            stu_user = User.query.filter_by(
                school_id=payment.school_id, username=student.admission_no
            ).first()
            if stu_user:
                send_notification(
                    stu_user.id,
                    payment.school_id,
                    f"Fee payment of K{payment.amount_paid:.2f} received (Receipt: {payment.reference}).",
                    "fee",
                )
        from utils import record_activity
        adm_label = student.admission_no if student else f"ID:{payment.student_id}"
        record_activity(
            "payment",
            "fee_payment_confirmed",
            f"School fee payment confirmed ({adm_label}) — K{float(payment.amount_paid or 0):.2f} (Receipt: {payment.reference}).",
            school_id=payment.school_id,
            status="success",
            target_type="payment",
            target_id=payment.reference or payment.lipila_reference_id,
            commit=False,
        )
        db.session.commit()
        logger.info(
            "Fee payment completed ref=%s receipt=%s student_id=%s amount=%.2f",
            payment.lipila_reference_id,
            payment.reference,
            payment.student_id,
            payment.amount_paid,
        )
    elif new_status == "failed":
        payment.status = "failed"
        from utils import record_activity
        record_activity(
            "payment",
            "fee_payment_failed",
            f"School fee payment failed — K{float(payment.amount_paid or 0):.2f} ({payment.lipila_reference_id}).",
            school_id=payment.school_id,
            status="failed",
            target_type="payment",
            target_id=payment.lipila_reference_id,
            commit=False,
        )
        db.session.commit()
        logger.info("Fee payment failed ref=%s student_id=%s", payment.lipila_reference_id, payment.student_id)

    return payment


# ══════════════════════════════════════════════════════════════════
#  A. SCHOOL SAAS SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════════

@billing.route("/plans")
@login_required
def plans():
    school = _get_current_school_or_403()
    prices = current_app.config["PLAN_PRICES"]
    limits = current_app.config["PLAN_LIMITS"]
    features = current_app.config["PLAN_FEATURES"]
    subs = (
        Subscription.query.filter_by(school_id=school.id)
        .order_by(Subscription.created_at.desc())
        .limit(10)
        .all()
    )
    client = LipilaClient()
    return render_template(
        "billing/plans.html",
        school=school,
        prices=prices,
        limits=limits,
        features=features,
        subs=subs,
        simulator_mode=client.simulator_enabled,
    )


@billing.route("/checkout/<plan>/<cycle>", methods=["POST"])
@login_required
@admin_required
def checkout(plan, cycle):
    school = _get_current_school_or_403()
    prices = current_app.config["PLAN_PRICES"]

    if plan not in prices or plan == "free" or cycle not in ("monthly", "yearly"):
        flash("Invalid subscription plan or billing cycle selected.", "danger")
        return redirect(url_for("billing.plans"))

    amount_key = "amount_yearly" if cycle == "yearly" else "amount_monthly"
    amount = float(prices[plan].get(amount_key, 0))
    currency = prices[plan].get("currency", "ZMW")
    if amount <= 0:
        flash("Invalid plan price configuration.", "danger")
        return redirect(url_for("billing.plans"))

    payment_method = request.form.get("payment_method", "mobile_money").strip().lower()
    phone_number = request.form.get("phone_number", "").strip() or school.phone or ""

    if payment_method not in ("mobile_money", "card"):
        flash("Please select Mobile Money or Card payment.", "danger")
        return redirect(url_for("billing.plans"))

    client = LipilaClient()
    reference_id = client.generate_reference("SUB")

    sub = Subscription(
        school_id=school.id,
        lipila_reference_id=reference_id,
        payment_method=payment_method,
        account_number=normalize_zambia_phone(phone_number) if phone_number else None,
        plan=plan,
        billing_cycle=cycle,
        amount=amount,
        currency=currency,
        status="pending",
        is_sandbox_simulated=client.simulator_enabled,
    )
    db.session.add(sub)
    db.session.commit()

    callback_url = current_app.config.get("LIPILA_CALLBACK_URL") or url_for(
        "billing.webhook_lipila", _external=True
    )
    back_url = url_for("billing.payment_status", reference_id=reference_id, _external=True)
    narration = f"EduManage {plan.title()} ({cycle}) - {school.name}"

    try:
        if payment_method == "mobile_money":
            res = client.initiate_mobile_money_collection(
                reference_id=reference_id,
                amount=amount,
                phone_number=phone_number,
                narration=narration,
                email=school.email,
                callback_url=callback_url,
            )
        else:
            res = client.initiate_card_collection(
                reference_id=reference_id,
                amount=amount,
                customer_info={
                    "first_name": school.name,
                    "last_name": "Admin",
                    "phone_number": phone_number,
                    "email": school.email,
                    "address": school.address or "Lusaka, Zambia",
                },
                narration=narration,
                back_url=back_url,
                callback_url=callback_url,
                reference_data=f"school_id={school.id};plan={plan};cycle={cycle}",
            )

        sub.lipila_transaction_id = res.get("transaction_id")
        sub.is_sandbox_simulated = bool(res.get("is_simulated"))
        db.session.commit()

        if res.get("redirect_url"):
            return redirect(res["redirect_url"], code=303)

        flash(res.get("message", "Payment initiated. Please confirm on your device."), "info")
        return redirect(url_for("billing.payment_status", reference_id=reference_id))

    except LipilaError as exc:
        sub.status = "failed"
        db.session.commit()
        flash(str(exc), "danger")
        return redirect(url_for("billing.plans"))


# ══════════════════════════════════════════════════════════════════
#  B. PARENT / STUDENT SCHOOL FEE PAYMENTS
# ══════════════════════════════════════════════════════════════════

@billing.route("/fee-checkout/<int:student_id>/<int:term_id>", methods=["GET", "POST"])
@login_required
def fee_checkout(student_id, term_id):
    student, school = _authorize_student_fee_access(student_id)
    term = Term.query.filter_by(id=term_id, school_id=school.id).first_or_404()
    balance = calculate_balance(student.id, term.id, school.id)
    client = LipilaClient()

    if request.method == "POST":
        if balance <= 0:
            flash("This term's fees are already paid in full.", "info")
            return redirect(
                url_for("parent.fees", student_id=student.id)
                if current_user.role == "parent"
                else url_for("student.fees")
            )

        amount_raw = request.form.get("amount", "")
        payment_method = request.form.get("payment_method", "mobile_money").strip().lower()
        phone_number = request.form.get("phone_number", "").strip()

        try:
            amount = round(float(amount_raw), 2)
        except (TypeError, ValueError):
            flash("Please enter a valid payment amount.", "danger")
            return redirect(url_for("billing.fee_checkout", student_id=student.id, term_id=term.id))

        if amount <= 0 or amount > balance:
            flash(f"Amount must be between K1.00 and K{balance:.2f}.", "danger")
            return redirect(url_for("billing.fee_checkout", student_id=student.id, term_id=term.id))

        if payment_method not in ("mobile_money", "card"):
            flash("Please select Mobile Money or Card payment.", "danger")
            return redirect(url_for("billing.fee_checkout", student_id=student.id, term_id=term.id))

        reference_id = client.generate_reference("FEE")
        narration = f"School Fees {term.name} - {student.admission_no}"

        payment = Payment(
            school_id=school.id,
            student_id=student.id,
            term_id=term.id,
            amount_paid=amount,
            currency="ZMW",
            reference=None,  # Generated only after verified payment completion
            lipila_reference_id=reference_id,
            payment_method=payment_method,
            account_number=normalize_zambia_phone(phone_number) if phone_number else None,
            narration=narration,
            status="pending",
            is_sandbox_simulated=client.simulator_enabled,
        )
        db.session.add(payment)
        db.session.commit()

        callback_url = current_app.config.get("LIPILA_CALLBACK_URL") or url_for(
            "billing.webhook_lipila", _external=True
        )
        back_url = url_for("billing.payment_status", reference_id=reference_id, _external=True)

        try:
            if payment_method == "mobile_money":
                res = client.initiate_mobile_money_collection(
                    reference_id=reference_id,
                    amount=amount,
                    phone_number=phone_number,
                    narration=narration,
                    email=current_user.email or school.email,
                    callback_url=callback_url,
                )
            else:
                res = client.initiate_card_collection(
                    reference_id=reference_id,
                    amount=amount,
                    customer_info={
                        "first_name": student.first_name,
                        "last_name": student.last_name,
                        "phone_number": phone_number,
                        "email": current_user.email or school.email,
                        "address": student.address or school.address or "Lusaka, Zambia",
                    },
                    narration=narration,
                    back_url=back_url,
                    callback_url=callback_url,
                    reference_data=f"school_id={school.id};student_id={student.id};term_id={term.id}",
                )

            payment.lipila_transaction_id = res.get("transaction_id")
            payment.is_sandbox_simulated = bool(res.get("is_simulated"))
            db.session.commit()

            if res.get("redirect_url"):
                return redirect(res["redirect_url"], code=303)

            flash(res.get("message", "Payment initiated. Please confirm on your phone."), "info")
            return redirect(url_for("billing.payment_status", reference_id=reference_id))

        except LipilaError as exc:
            payment.status = "failed"
            db.session.commit()
            flash(str(exc), "danger")
            return redirect(url_for("billing.fee_checkout", student_id=student.id, term_id=term.id))

    return render_template(
        "billing/fee_checkout.html",
        student=student,
        term=term,
        school=school,
        balance=balance,
        simulator_mode=client.simulator_enabled,
    )


# ══════════════════════════════════════════════════════════════════
#  STATUS RECONCILIATION & SANDBOX SIMULATOR
# ══════════════════════════════════════════════════════════════════

def _lookup_transaction(reference_id: str):
    """Find either a Subscription or a Payment by lipila_reference_id."""
    sub = Subscription.query.filter_by(lipila_reference_id=reference_id).first()
    if sub:
        return "subscription", sub
    pay = Payment.query.filter_by(lipila_reference_id=reference_id).first()
    if pay:
        return "fee", pay
    return None, None


def _verify_record_access(kind: str, record):
    """Ensure the current user belongs to the same school as the transaction record."""
    if current_user.is_superadmin:
        return
    school_id = get_current_school_id(required=True)
    if record.school_id != school_id:
        abort(403)
    if kind == "fee" and current_user.role in ("student", "parent"):
        _authorize_student_fee_access(record.student_id)


@billing.route("/status/<reference_id>")
@login_required
def payment_status(reference_id):
    """
    Display transaction status. Never trusts query parameters to mark a payment as paid.
    If pending and live Lipila credentials are configured, polls Lipila's status endpoint.
    """
    kind, record = _lookup_transaction(reference_id)
    if not record:
        abort(404)
    _verify_record_access(kind, record)

    client = LipilaClient()
    if record.status == "pending" and not client.simulator_enabled and client.api_key:
        try:
            status_info = client.check_transaction_status(reference_id)
            remote_status = status_info.get("status", "pending")
            remote_amount = status_info.get("amount")
            expected_amount = record.amount if kind == "subscription" else record.amount_paid

            if remote_status == "completed":
                if remote_amount is None or abs(float(remote_amount) - float(expected_amount)) < 0.01:
                    if kind == "subscription":
                        _settle_subscription(record, "completed", status_info.get("transaction_id"))
                    else:
                        _settle_fee_payment(record, "completed", status_info.get("transaction_id"))
            elif remote_status == "failed":
                if kind == "subscription":
                    _settle_subscription(record, "failed", status_info.get("transaction_id"))
                else:
                    _settle_fee_payment(record, "failed", status_info.get("transaction_id"))
        except LipilaError:
            pass

    return render_template(
        "billing/status.html",
        kind=kind,
        record=record,
        reference_id=reference_id,
        simulator_mode=client.simulator_enabled,
    )


@billing.route("/reconcile/<reference_id>", methods=["POST"])
@login_required
def reconcile_status(reference_id):
    """Explicit server-to-server status reconciliation with Lipila."""
    kind, record = _lookup_transaction(reference_id)
    if not record:
        abort(404)
    _verify_record_access(kind, record)

    if record.status in ("completed", "active"):
        flash("Payment is already confirmed.", "success")
        return redirect(url_for("billing.payment_status", reference_id=reference_id))

    client = LipilaClient()
    if client.simulator_enabled and not client.api_key:
        flash("In Sandbox Simulator mode, use the Sandbox Simulator screen to complete or fail the test payment.", "info")
        return redirect(url_for("billing.sandbox_checkout", reference_id=reference_id))

    try:
        status_info = client.check_transaction_status(reference_id)
        remote_status = status_info.get("status", "pending")
        remote_amount = status_info.get("amount")
        expected_amount = record.amount if kind == "subscription" else record.amount_paid

        if remote_status == "completed":
            if remote_amount is not None and abs(float(remote_amount) - float(expected_amount)) >= 0.01:
                flash("Payment amount mismatch detected during reconciliation.", "danger")
                return redirect(url_for("billing.payment_status", reference_id=reference_id))

            if kind == "subscription":
                _settle_subscription(record, "completed", status_info.get("transaction_id"))
                flash("Subscription payment verified and activated!", "success")
            else:
                _settle_fee_payment(record, "completed", status_info.get("transaction_id"))
                flash(f"Fee payment verified! Receipt {record.reference} generated.", "success")
        elif remote_status == "failed":
            if kind == "subscription":
                _settle_subscription(record, "failed", status_info.get("transaction_id"))
            else:
                _settle_fee_payment(record, "failed", status_info.get("transaction_id"))
            flash("Payment was declined or failed.", "danger")
        else:
            flash("Payment is still pending confirmation. Please complete the prompt on your phone.", "warning")
    except LipilaError as exc:
        flash(str(exc), "warning")

    return redirect(url_for("billing.payment_status", reference_id=reference_id))


@billing.route("/sandbox/<reference_id>", methods=["GET", "POST"])
@login_required
def sandbox_checkout(reference_id):
    """
    Development/Testing Sandbox Simulator.
    Strictly disabled in production environments.
    """
    client = LipilaClient()
    if current_app.config.get("IS_PRODUCTION") or not client.simulator_enabled:
        abort(403)

    kind, record = _lookup_transaction(reference_id)
    if not record:
        abort(404)
    _verify_record_access(kind, record)

    if request.method == "POST":
        action = request.form.get("action", "")
        sim_tx_id = record.lipila_transaction_id or f"SIM-{reference_id}"
        if action == "approve":
            if kind == "subscription":
                _settle_subscription(record, "completed", sim_tx_id, is_simulated=True)
                flash("TEST MODE: Simulated subscription payment approved.", "success")
            else:
                _settle_fee_payment(record, "completed", sim_tx_id, is_simulated=True)
                flash(f"TEST MODE: Simulated fee payment approved (Test Receipt: {record.reference}).", "success")
        elif action == "decline":
            if kind == "subscription":
                _settle_subscription(record, "failed", sim_tx_id, is_simulated=True)
            else:
                _settle_fee_payment(record, "failed", sim_tx_id, is_simulated=True)
            flash("TEST MODE: Simulated payment declined.", "warning")

        return redirect(url_for("billing.payment_status", reference_id=reference_id))

    return render_template(
        "billing/sandbox_simulator.html",
        kind=kind,
        record=record,
        reference_id=reference_id,
    )


# ── Checkout Success / Expired / Cancel ───────────────────────────
@billing.route("/success")
@login_required
def success():
    reference_id = request.args.get("reference_id") or request.args.get("referenceId")
    if reference_id:
        return redirect(url_for("billing.payment_status", reference_id=reference_id))
    return render_template("billing/success.html")


@billing.route("/expired")
def expired():
    school = getattr(g, "school", None)
    return render_template("billing/expired.html", school=school)


@billing.route("/cancel", methods=["POST"])
@login_required
@admin_required
def cancel():
    school = _get_current_school_or_403()
    if school.plan == "free":
        flash("You are currently on the Free plan.", "info")
        return redirect(url_for("billing.plans"))

    school.plan = "free"
    school.lipila_subscription_ref = None
    school.stripe_subscription_id = None
    db.session.commit()
    flash("Your subscription has been cancelled and reverted to the Free tier.", "info")
    return redirect(url_for("billing.plans"))


# ══════════════════════════════════════════════════════════════════
#  LIPILA WEBHOOK ENDPOINT
# ══════════════════════════════════════════════════════════════════

@billing.route("/webhook/lipila", methods=["POST"])
@billing.route("/webhook", methods=["POST"])
@csrf.exempt
def webhook_lipila():
    """
    Asynchronous Lipila payment callback handler.
    Verifies authenticity, validates amount/currency, and idempotently settles
    subscriptions or school fee payments.
    """
    client = LipilaClient()
    if not client.verify_webhook_request(request.data, request.headers):
        logger.warning("Rejected unverified Lipila webhook call.")
        return jsonify({"error": "Invalid webhook signature or credentials"}), 401

    payload = request.get_json(silent=True) or {}
    reference_id = (
        payload.get("referenceId")
        or payload.get("reference_id")
        or payload.get("collectionRequest", {}).get("referenceId")
        or ""
    ).strip()

    if not reference_id:
        return jsonify({"error": "Missing referenceId"}), 400

    kind, record = _lookup_transaction(reference_id)
    if not record:
        logger.warning("Lipila webhook received for unknown referenceId=%s", reference_id)
        return jsonify({"error": "Transaction reference not found"}), 404

    # Idempotency check: if already completed/active, return 200 immediately
    if record.status in ("completed", "active"):
        return jsonify({"status": "already_processed", "referenceId": reference_id}), 200

    raw_status = str(
        payload.get("status")
        or payload.get("transactionStatus")
        or "pending"
    )
    norm_status = client._normalize_status(raw_status)
    tx_id = payload.get("transactionId") or payload.get("id") or record.lipila_transaction_id

    # Validate amount & currency against server-stored record
    expected_amount = record.amount if kind == "subscription" else record.amount_paid
    expected_currency = (record.currency or "ZMW").upper()

    webhook_amount = payload.get("amount")
    webhook_currency = (payload.get("currency") or expected_currency).upper()

    if webhook_currency != expected_currency:
        logger.error("Lipila webhook currency mismatch ref=%s got=%s expected=%s", reference_id, webhook_currency, expected_currency)
        return jsonify({"error": "Currency mismatch"}), 400

    if webhook_amount is not None:
        try:
            if abs(float(webhook_amount) - float(expected_amount)) >= 0.01:
                logger.error(
                    "Lipila webhook amount mismatch ref=%s got=%s expected=%s",
                    reference_id,
                    webhook_amount,
                    expected_amount,
                )
                return jsonify({"error": "Amount mismatch"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid amount"}), 400

    if norm_status == "completed":
        if kind == "subscription":
            _settle_subscription(record, "completed", tx_id, is_simulated=record.is_sandbox_simulated)
        else:
            _settle_fee_payment(record, "completed", tx_id, is_simulated=record.is_sandbox_simulated)
    elif norm_status == "failed":
        if kind == "subscription":
            _settle_subscription(record, "failed", tx_id, is_simulated=record.is_sandbox_simulated)
        else:
            _settle_fee_payment(record, "failed", tx_id, is_simulated=record.is_sandbox_simulated)

    return jsonify({"status": "ok", "referenceId": reference_id, "settledStatus": record.status}), 200
