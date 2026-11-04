"""
tests/test_edumanage.py — Comprehensive test suite covering:
- Phase 2: Application startup, route registration, and template rendering
- Phase 3: Multi-tenant isolation & role/ownership authorization
- Phase 4: Lipila SaaS subscription & student fee payments, webhooks, idempotency, reconciliation, and sandbox simulator guards
- Phase 5: Non-destructive database schema migration preserving legacy Stripe data
- Phase 6 & 7: PWA assets, security/cache headers, and Firebase/Cloud Run deployment configuration
"""
import hmac
import hashlib
import json
import datetime
import pytest
from unittest.mock import patch
from app import create_app
from extensions import db
from models import (
    School,
    User,
    SchoolClass,
    Student,
    Teacher,
    Parent,
    ParentStudent,
    Subject,
    Term,
    Exam,
    FeeStructure,
    Payment,
    Subscription,
    Announcement,
    Assignment,
    Submission,
    Result,
    Attendance,
    TeacherAssignment,
    utc_now,
)
from utils import calculate_balance


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test_edumanage.db"
    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-secret-key",
        "UPLOAD_FOLDER": str(tmp_path / "uploads" / "materials"),
        "ASSIGNMENT_UPLOAD": str(tmp_path / "uploads" / "assignments"),
        "ANNOUNCEMENT_UPLOAD": str(tmp_path / "uploads" / "announcements"),
        "RATELIMIT_ENABLED": False,
        "IS_PRODUCTION": False,
        "LIPILA_ENV": "sandbox",
        "LIPILA_API_KEY": "",
        "LIPILA_WEBHOOK_SECRET": "test-webhook-secret",
        "LIPILA_SIMULATOR_ENABLED": True,
    }
    application = create_app(test_config)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_two_schools(app):
    """Create two separate schools (School A and School B) with admins, teachers, classes, students, and parents."""
    with app.app_context():
        active_until = utc_now() + datetime.timedelta(days=30)
        school_a = School(
            name="Lusaka High",
            subdomain="lusakahigh",
            email="admin@lusakahigh.zm",
            plan="growth",
            subscription_ends_at=active_until,
        )
        school_b = School(
            name="Ndola Academy",
            subdomain="ndolaacademy",
            email="admin@ndola.zm",
            plan="starter",
            subscription_ends_at=active_until,
        )
        db.session.add_all([school_a, school_b])
        db.session.flush()

        admin_a = User(school_id=school_a.id, username="admin", email="admin@lusakahigh.zm", role="admin", is_verified=True)
        admin_a.set_password("AdminPass123")
        admin_b = User(school_id=school_b.id, username="admin", email="admin@ndola.zm", role="admin", is_verified=True)
        admin_b.set_password("AdminPass123")
        db.session.add_all([admin_a, admin_b])

        class_a = SchoolClass(school_id=school_a.id, name="Grade 10A", capacity=40)
        class_b = SchoolClass(school_id=school_b.id, name="Grade 10B", capacity=35)
        db.session.add_all([class_a, class_b])

        term_a = Term(
            school_id=school_a.id,
            name="Term 1 2026",
            start_date=datetime.date(2026, 1, 10),
            end_date=datetime.date(2026, 4, 10),
        )
        term_b = Term(
            school_id=school_b.id,
            name="Term 1 2026",
            start_date=datetime.date(2026, 1, 10),
            end_date=datetime.date(2026, 4, 10),
        )
        db.session.add_all([term_a, term_b])
        db.session.flush()

        fee_a = FeeStructure(school_id=school_a.id, class_id=class_a.id, term_id=term_a.id, amount=2500.0)
        fee_b = FeeStructure(school_id=school_b.id, class_id=class_b.id, term_id=term_b.id, amount=3000.0)
        db.session.add_all([fee_a, fee_b])

        stu_a1 = Student(school_id=school_a.id, admission_no="LH001", first_name="Chanda", last_name="Mwale", gender="Female", class_id=class_a.id)
        stu_a2 = Student(school_id=school_a.id, admission_no="LH002", first_name="Mutale", last_name="Banda", gender="Male", class_id=class_a.id)
        stu_b1 = Student(school_id=school_b.id, admission_no="NA001", first_name="Bwalya", last_name="Phiri", gender="Male", class_id=class_b.id)
        db.session.add_all([stu_a1, stu_a2, stu_b1])
        db.session.flush()

        u_stu_a1 = User(school_id=school_a.id, username="LH001", role="student", student_id=stu_a1.id, is_verified=True)
        u_stu_a1.set_password("student123")
        u_stu_b1 = User(school_id=school_b.id, username="NA001", role="student", student_id=stu_b1.id, is_verified=True)
        u_stu_b1.set_password("student123")
        db.session.add_all([u_stu_a1, u_stu_b1])

        u_parent_a = User(school_id=school_a.id, username="parent_chanda", role="parent", is_verified=True)
        u_parent_a.set_password("parent123")
        db.session.add(u_parent_a)
        db.session.flush()

        parent_a = Parent(school_id=school_a.id, user_id=u_parent_a.id, first_name="Mary", last_name="Mwale", phone="0977111222")
        db.session.add(parent_a)
        db.session.flush()

        # Link parent_a ONLY to stu_a1 (not stu_a2, not stu_b1)
        link_a = ParentStudent(school_id=school_a.id, parent_id=parent_a.id, student_id=stu_a1.id)
        db.session.add(link_a)

        u_teacher_a = User(school_id=school_a.id, username="ST1001", role="teacher", is_verified=True)
        u_teacher_a.set_password("teacher123")
        db.session.add(u_teacher_a)
        db.session.flush()

        teacher_a = Teacher(school_id=school_a.id, user_id=u_teacher_a.id, staff_no="ST1001", first_name="Grace", last_name="Tembo", phone="0977999888")
        db.session.add(teacher_a)
        db.session.commit()

        return {
            "school_a_id": school_a.id,
            "school_b_id": school_b.id,
            "class_a_id": class_a.id,
            "class_b_id": class_b.id,
            "term_a_id": term_a.id,
            "term_b_id": term_b.id,
            "stu_a1_id": stu_a1.id,
            "stu_a2_id": stu_a2.id,
            "stu_b1_id": stu_b1.id,
        }


def login(client, username, password, school_subdomain=""):
    return client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "school_subdomain": school_subdomain,
        },
        follow_redirects=True,
    )


# ══════════════════════════════════════════════════════════════════
#  PHASE 2 & 6 & 7: STARTUP, CORE ROUTES, PWA & CONFIG
# ══════════════════════════════════════════════════════════════════

def test_public_pwa_and_health_routes(client):
    assert client.get("/").status_code == 200
    assert client.get("/pricing").status_code == 200
    assert client.get("/register").status_code == 200
    assert client.get("/login").status_code == 200

    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "healthy"

    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    m_data = json.loads(manifest.data)
    manifest.close()
    assert m_data["theme_color"] == "#1e293b"
    assert m_data["display"] == "standalone"

    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "no-store" in sw.headers.get("Cache-Control", "")
    sw.close()

    offline = client.get("/offline")
    assert offline.status_code == 200


def test_school_onboarding_and_shared_domain_selection(client, app):
    resp = client.post(
        "/register",
        data={
            "school_name": "Copperbelt School",
            "subdomain": "copperbelt",
            "email": "admin@copperbelt.zm",
            "phone": "0977123456",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Copperbelt School" in resp.data

    # Test shared-domain selector (/s/copperbelt)
    sel = client.get("/s/copperbelt", follow_redirects=True)
    assert sel.status_code == 200
    assert b"Copperbelt School" in sel.data


# ══════════════════════════════════════════════════════════════════
#  PHASE 3: MULTI-TENANT SECURITY & OWNERSHIP ISOLATION
# ══════════════════════════════════════════════════════════════════

def test_cross_school_isolation_for_admins(client, seed_two_schools):
    ids = seed_two_schools
    # Log in as Admin of School A (lusakahigh)
    resp = login(client, "admin", "AdminPass123", "lusakahigh")
    assert resp.status_code == 200

    # Admin A can access Student A1 fee recording
    assert client.get(f"/admin/pay-fees/{ids['stu_a1_id']}").status_code == 200

    # Admin A MUST BE DENIED (404/403) when trying to access School B's Student B1
    assert client.get(f"/admin/pay-fees/{ids['stu_b1_id']}").status_code == 404

    # Admin A MUST BE DENIED when trying to view School B's class timetable
    assert client.get(f"/admin/timetable/{ids['class_b_id']}").status_code == 404

    # Admin A cannot register a student into School B's class
    bad_reg = client.post(
        "/admin/register-student",
        data={
            "first_name": "Intruder",
            "last_name": "Student",
            "admission_no": "INT001",
            "gender": "Male",
            "class_id": ids["class_b_id"],
        },
        follow_redirects=True,
    )
    assert b"does not belong to your school" in bad_reg.data


def test_parent_and_student_record_ownership(client, seed_two_schools):
    ids = seed_two_schools
    # Log in as Parent A (linked only to stu_a1)
    login(client, "parent_chanda", "parent123", "lusakahigh")

    # Parent A can view linked child stu_a1
    assert client.get(f"/parent/results/{ids['stu_a1_id']}").status_code == 200
    assert client.get(f"/parent/attendance/{ids['stu_a1_id']}").status_code == 200
    assert client.get(f"/parent/fees/{ids['stu_a1_id']}").status_code == 200
    assert client.get(f"/billing/fee-checkout/{ids['stu_a1_id']}/{ids['term_a_id']}").status_code == 200

    # Parent A MUST BE DENIED (403) when accessing unlinked student stu_a2 in the SAME school
    assert client.get(f"/parent/results/{ids['stu_a2_id']}").status_code == 403
    assert client.get(f"/parent/fees/{ids['stu_a2_id']}").status_code == 403
    assert client.get(f"/billing/fee-checkout/{ids['stu_a2_id']}/{ids['term_a_id']}").status_code == 403

    # Parent A MUST BE DENIED (404) when accessing student stu_b1 in School B
    assert client.get(f"/parent/results/{ids['stu_b1_id']}").status_code == 404
    assert client.get(f"/billing/fee-checkout/{ids['stu_b1_id']}/{ids['term_b_id']}").status_code == 404

    client.get("/logout")

    # Log in as Student A1
    login(client, "LH001", "student123", "lusakahigh")
    assert client.get(f"/student/report-card/{ids['stu_a1_id']}/{ids['term_a_id']}").status_code == 200
    # Student A1 cannot view Student A2's report card or School B's report card
    assert client.get(f"/student/report-card/{ids['stu_a2_id']}/{ids['term_a_id']}").status_code == 403
    assert client.get(f"/student/report-card/{ids['stu_b1_id']}/{ids['term_b_id']}").status_code == 404


def test_teacher_cross_school_isolation(client, seed_two_schools):
    ids = seed_two_schools
    login(client, "ST1001", "teacher123", "lusakahigh")

    # Teacher A can open attendance for Class A
    assert client.get(f"/teacher/attendance/{ids['class_a_id']}").status_code == 200
    # Teacher A is denied (404) for School B's Class B
    assert client.get(f"/teacher/attendance/{ids['class_b_id']}").status_code == 404


# ══════════════════════════════════════════════════════════════════
#  PHASE 4: LIPILA PAYMENTS, WEBHOOKS, RECONCILIATION & SIMULATOR
# ══════════════════════════════════════════════════════════════════

def _sign_webhook(payload_dict: dict, secret: str = "test-webhook-secret"):
    raw = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, {"Content-Type": "application/json", "X-Lipila-Signature": sig}


def test_lipila_subscription_checkout_and_webhook_verification(client, app, seed_two_schools):
    ids = seed_two_schools
    login(client, "admin", "AdminPass123", "ndolaacademy")

    # Initiate upgrade from starter -> enterprise (monthly) via Lipila Mobile Money
    resp = client.post(
        "/billing/checkout/enterprise/monthly",
        data={"payment_method": "mobile_money", "phone_number": "0977123456"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    with app.app_context():
        sub = Subscription.query.filter_by(school_id=ids["school_b_id"]).first()
        assert sub is not None
        assert sub.status == "pending"
        assert sub.plan == "enterprise"
        assert sub.amount == 2200.0
        assert sub.currency == "ZMW"
        ref_id = sub.lipila_reference_id
        # Plan must NOT be upgraded while payment is still pending
        school_b = db.session.get(School, ids["school_b_id"])
        assert school_b.plan == "starter"

    # Visiting status page with fake query param ?status=success MUST NOT activate subscription
    client.get(f"/billing/status/{ref_id}?status=success")
    with app.app_context():
        assert db.session.get(School, ids["school_b_id"]).plan == "starter"

    # Unsigned / wrong-signature webhook MUST be rejected with 401
    bad_wh = client.post(
        "/billing/webhook/lipila",
        data=json.dumps({"referenceId": ref_id, "status": "Successful", "amount": 2200.0, "currency": "ZMW"}),
        headers={"Content-Type": "application/json", "X-Lipila-Signature": "invalid-sig"},
    )
    assert bad_wh.status_code == 401

    # Tampered amount webhook MUST be rejected with 400
    raw_bad_amt, hdrs_bad_amt = _sign_webhook(
        {"referenceId": ref_id, "status": "Successful", "amount": 10.0, "currency": "ZMW"}
    )
    assert client.post("/billing/webhook/lipila", data=raw_bad_amt, headers=hdrs_bad_amt).status_code == 400

    # Valid signed Lipila webhook activates subscription
    raw_ok, hdrs_ok = _sign_webhook(
        {"referenceId": ref_id, "transactionId": "LPL-TX-999", "status": "Successful", "amount": 2200.0, "currency": "ZMW"}
    )
    wh_ok = client.post("/billing/webhook/lipila", data=raw_ok, headers=hdrs_ok)
    assert wh_ok.status_code == 200
    assert wh_ok.get_json()["settledStatus"] == "active"

    with app.app_context():
        school_b = db.session.get(School, ids["school_b_id"])
        assert school_b.plan == "enterprise"

    # Duplicate webhook callback is idempotent
    wh_dup = client.post("/billing/webhook/lipila", data=raw_ok, headers=hdrs_ok)
    assert wh_dup.status_code == 200
    assert wh_dup.get_json()["status"] == "already_processed"


def test_lipila_student_fee_payment_reconciliation_and_receipt(client, app, seed_two_schools):
    ids = seed_two_schools
    login(client, "parent_chanda", "parent123", "lusakahigh")

    # Initial balance for stu_a1 in term_a is K2,500.00
    with app.app_context():
        assert calculate_balance(ids["stu_a1_id"], ids["term_a_id"], ids["school_a_id"]) == 2500.0

    # Initiate partial payment of K1,000.00 via Lipila Mobile Money
    resp = client.post(
        f"/billing/fee-checkout/{ids['stu_a1_id']}/{ids['term_a_id']}",
        data={"amount": "1000.00", "payment_method": "mobile_money", "phone_number": "0966123456"},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    with app.app_context():
        payment = Payment.query.filter_by(student_id=ids["stu_a1_id"]).first()
        assert payment is not None
        assert payment.status == "pending"
        assert payment.reference is None
        pay_id = payment.id
        ref_id = payment.lipila_reference_id
        # Pending payment MUST NOT reduce student balance
        assert calculate_balance(ids["stu_a1_id"], ids["term_a_id"], ids["school_a_id"]) == 2500.0

    # Receipt page MUST NOT render while payment is pending
    rcpt_pending = client.get(f"/admin/receipt/{pay_id}", follow_redirects=False)
    assert rcpt_pending.status_code in (302, 403)

    # Confirm payment via Lipila webhook
    raw_ok, hdrs_ok = _sign_webhook(
        {"referenceId": ref_id, "transactionId": "LPL-FEE-777", "status": "Successful", "amount": 1000.0, "currency": "ZMW"}
    )
    wh = client.post("/billing/webhook/lipila", data=raw_ok, headers=hdrs_ok)
    assert wh.status_code == 200

    with app.app_context():
        payment = db.session.get(Payment, pay_id)
        assert payment.status == "completed"
        assert payment.reference is not None and payment.reference.startswith("RCT-")
        # Balance is now reduced to K1,500.00
        assert calculate_balance(ids["stu_a1_id"], ids["term_a_id"], ids["school_a_id"]) == 1500.0

    # Receipt page is now accessible to the authorized parent
    rcpt_ok = client.get(f"/admin/receipt/{pay_id}")
    assert rcpt_ok.status_code == 200
    assert b"RCT-" in rcpt_ok.data


def test_sandbox_simulator_blocked_in_production(client, app, seed_two_schools):
    ids = seed_two_schools
    login(client, "parent_chanda", "parent123", "lusakahigh")

    client.post(
        f"/billing/fee-checkout/{ids['stu_a1_id']}/{ids['term_a_id']}",
        data={"amount": "500.00", "payment_method": "card", "phone_number": "0977111222"},
    )
    with app.app_context():
        payment = Payment.query.filter_by(student_id=ids["stu_a1_id"]).first()
        ref_id = payment.lipila_reference_id

    # Simulate production environment flag
    app.config["IS_PRODUCTION"] = True
    assert client.get(f"/billing/sandbox/{ref_id}").status_code == 403
    assert client.post(f"/billing/sandbox/{ref_id}", data={"action": "approve"}).status_code == 403


def test_lipila_live_api_status_reconciliation_mock(client, app, seed_two_schools):
    """Test server-to-server reconciliation against Lipila /collections/check-status."""
    ids = seed_two_schools
    app.config["LIPILA_SIMULATOR_ENABLED"] = False
    app.config["LIPILA_API_KEY"] = "test-live-key"

    with app.app_context():
        p = Payment(
            school_id=ids["school_a_id"],
            student_id=ids["stu_a1_id"],
            term_id=ids["term_a_id"],
            amount_paid=800.0,
            currency="ZMW",
            lipila_reference_id="FEE-RECON-001",
            payment_method="mobile_money",
            status="pending",
        )
        db.session.add(p)
        db.session.commit()

    login(client, "parent_chanda", "parent123", "lusakahigh")

    with patch("services.lipila.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b'{"status":"Successful"}'
        mock_get.return_value.json.return_value = {
            "referenceId": "FEE-RECON-001",
            "transactionId": "LPL-9001",
            "status": "Successful",
            "amount": 800.0,
            "currency": "ZMW",
        }
        resp = client.post("/billing/reconcile/FEE-RECON-001", follow_redirects=True)
        assert resp.status_code == 200

    with app.app_context():
        updated = Payment.query.filter_by(lipila_reference_id="FEE-RECON-001").first()
        assert updated.status == "completed"
        assert updated.reference.startswith("RCT-")
        assert calculate_balance(ids["stu_a1_id"], ids["term_a_id"], ids["school_a_id"]) == 1700.0


# ══════════════════════════════════════════════════════════════════
#  PHASE 5 & 8: MIGRATION PRESERVATION, AUTH & EXPIRED SUBSCRIPTIONS
# ══════════════════════════════════════════════════════════════════

def test_password_change_and_role_guards(client, seed_two_schools):
    # Student cannot access /admin or /superadmin
    login(client, "LH001", "student123", "lusakahigh")
    assert client.get("/admin/dashboard").status_code == 403
    assert client.get("/superadmin/").status_code == 403

    # Student can change password
    chg = client.post(
        "/change-password",
        data={
            "current_password": "student123",
            "new_password": "NewStudentPass99",
            "confirm_password": "NewStudentPass99",
        },
        follow_redirects=True,
    )
    assert chg.status_code == 200
    assert b"Password changed successfully" in chg.data

    client.get("/logout")
    # Login with new password succeeds
    relogin = login(client, "LH001", "NewStudentPass99", "lusakahigh")
    assert relogin.status_code == 200
    assert b"Chanda" in relogin.data


def test_expired_subscription_redirects_to_billing_expired(client, app, seed_two_schools):
    ids = seed_two_schools
    with app.app_context():
        school_a = db.session.get(School, ids["school_a_id"])
        school_a.subscription_ends_at = utc_now() - datetime.timedelta(days=2)
        school_a.trial_ends_at = utc_now() - datetime.timedelta(days=10)
        db.session.commit()

    login(client, "admin", "AdminPass123", "lusakahigh")
    resp = client.get("/admin/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert "/billing/expired" in resp.headers["Location"]


def test_schema_migration_preserves_stripe_history(app, seed_two_schools):
    from migrations_helper import ensure_schema_columns

    ids = seed_two_schools
    with app.app_context():
        # Verify ensure_schema_columns is idempotent and legacy Stripe columns coexist with Lipila columns
        ensure_schema_columns(db)
        sub = Subscription(
            school_id=ids["school_a_id"],
            plan="growth",
            billing_cycle="monthly",
            amount=1200.0,
            currency="ZMW",
            status="active",
            stripe_subscription_id="sub_legacy_stripe_123",
            stripe_invoice_id="in_legacy_stripe_123",
            lipila_reference_id="SUB-NEW-LIPILA-123",
        )
        db.session.add(sub)
        db.session.commit()

        saved = Subscription.query.filter_by(lipila_reference_id="SUB-NEW-LIPILA-123").first()
        assert saved is not None
        assert saved.stripe_subscription_id == "sub_legacy_stripe_123"
        assert saved.lipila_reference_id == "SUB-NEW-LIPILA-123"


def test_shadergradient_hero_and_brand_palette(client, seed_two_schools):
    # 1. Verify homepage hero includes isolated ShaderGradient mount with official 3 brand colours
    home = client.get("/")
    assert home.status_code == 200
    html = home.data.decode("utf-8")
    assert "--color-mustard: #FFB800;" in html
    assert "--color-strong-blue: #002583;" in html
    assert "--color-cool-gray: #E5E8EF;" in html
    assert 'class="shadergradient-mount"' in html
    assert 'data-color1="#002583"' in html
    assert 'data-color2="#FFB800"' in html
    assert 'data-color3="#E5E8EF"' in html
    assert 'data-pixel-density="1.0"' in html
    assert 'aria-hidden="true"' in html
    assert 'class="hero-readability-scrim"' in html

    # 2. Verify static brand CSS and ShaderGradient JS assets serve cleanly with safeguards
    css_resp = client.get("/static/css/brand-theme.css")
    assert css_resp.status_code == 200
    css_text = css_resp.data.decode("utf-8")
    assert "--color-mustard: #FFB800;" in css_text
    assert "--color-strong-blue: #002583;" in css_text
    assert "--color-cool-gray: #E5E8EF;" in css_text
    assert "pointer-events: none" in css_text
    assert "prefers-reduced-motion: reduce" in css_text

    js_resp = client.get("/static/js/shader-gradient-hero.js")
    assert js_resp.status_code == 200
    js_text = js_resp.data.decode("utf-8")
    assert "#002583" in js_text
    assert "#FFB800" in js_text
    assert "#E5E8EF" in js_text
    assert "prefers-reduced-motion: reduce" in js_text
    assert "webglcontextlost" in js_text
    assert "IntersectionObserver" in js_text

    # 3. Verify restraint: login and dashboards do not include animated WebGL mounts
    login_html = client.get("/login").data.decode("utf-8")
    assert 'class="shadergradient-mount"' not in login_html
    assert "--color-strong-blue: #002583;" in login_html


def test_react_api_endpoints_and_tenant_isolation(client, seed_two_schools):
    ids = seed_two_schools
    # 1. Public bootstrap endpoint
    boot = client.get("/api/bootstrap")
    assert boot.status_code == 200
    b_json = boot.get_json()
    assert b_json["authenticated"] is False
    assert len(b_json["schools"]) == 2

    # 2. API login as Admin of School A (lusakahigh)
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )
    assert login_resp.status_code == 200
    assert login_resp.get_json()["user"]["role"] == "admin"

    # 3. Admin overview returns ONLY School A's data (2 students, not School B's student)
    adm_ov = client.get("/api/admin/overview")
    assert adm_ov.status_code == 200
    ov_json = adm_ov.get_json()
    assert ov_json["metrics"]["total_students"] == 2
    student_admissions = {s["admission_no"] for s in ov_json["students"]}
    assert "LH001" in student_admissions
    assert "NA001" not in student_admissions

    # 4. Admin cannot access Superadmin API
    assert client.get("/api/superadmin/overview").status_code == 403

    # 5. API logout & Parent login -> Lipila fee checkout -> Sandbox approve -> Receipt API
    client.post("/api/auth/logout")
    par_login = client.post(
        "/api/auth/login",
        json={"username": "parent_chanda", "password": "parent123", "school_subdomain": "lusakahigh"},
    )
    assert par_login.status_code == 200

    par_ov = client.get("/api/parent/overview").get_json()
    assert len(par_ov["children"]) == 1
    assert par_ov["children"][0]["admission_no"] == "LH001"

    # Parent cannot checkout fees for unlinked student stu_a2
    bad_fee = client.post(
        "/api/billing/checkout-fee",
        json={
            "student_id": ids["stu_a2_id"],
            "term_id": ids["term_a_id"],
            "amount": 500,
            "payment_method": "mobile_money",
            "phone_number": "0977111222",
        },
    )
    assert bad_fee.status_code == 403

    # Parent initiates fee checkout for linked child stu_a1
    ok_fee = client.post(
        "/api/billing/checkout-fee",
        json={
            "student_id": ids["stu_a1_id"],
            "term_id": ids["term_a_id"],
            "amount": 600,
            "payment_method": "mobile_money",
            "phone_number": "0977111222",
        },
    )
    assert ok_fee.status_code == 200
    ref_id = ok_fee.get_json()["reference_id"]

    # Approve via Sandbox API and verify receipt
    sim_ok = client.post(f"/api/billing/sandbox/{ref_id}", json={"action": "approve"})
    assert sim_ok.status_code == 200
    sim_data = sim_ok.get_json()
    assert sim_data["status"] == "completed"
    assert sim_data["receipt_ref"].startswith("RCT-")

    rcpt = client.get(f"/api/billing/receipt/{sim_data['receipt_id']}")
    assert rcpt.status_code == 200
    assert rcpt.get_json()["remaining_balance"] == 1900.0

    # 6. Verify compiled React SPA is served on browser routes when TESTING is False
    client.application.config["TESTING"] = False
    try:
        spa_root = client.get("/")
        assert spa_root.status_code == 200
        assert '<div id="root"></div>' in spa_root.data.decode("utf-8")

        spa_login = client.get("/login")
        assert spa_login.status_code == 200
        assert '<div id="root"></div>' in spa_login.data.decode("utf-8")

        # 7. Verify /images/heropic.png asset route serves the actual root image
        hero_img = client.get("/images/heropic.png")
        assert hero_img.status_code == 200
        assert hero_img.mimetype == "image/png"
        assert len(hero_img.data) > 1000000
        hero_img.close()
    finally:
        client.application.config["TESTING"] = True


def test_superadmin_school_inspection_activity_and_audit_controls(client, seed_two_schools):
    ids = seed_two_schools

    # 1. Ordinary school users (admin, teacher, parent, student) cannot access any superadmin API
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )
    assert client.get("/api/superadmin/overview").status_code == 403
    assert client.get(f"/api/superadmin/schools/{ids['school_a_id']}").status_code == 403
    assert client.get("/api/superadmin/activity").status_code == 403
    assert client.post(
        f"/api/superadmin/schools/{ids['school_a_id']}/status",
        json={"action": "suspend", "reason": "Unauthorized test"},
    ).status_code == 403

    # Record a fee payment in School A so we can verify it is NOT counted as platform SaaS revenue
    pay_res = client.post(
        "/api/admin/manual-payment",
        json={
            "student_id": ids["stu_a1_id"],
            "term_id": ids["term_a_id"],
            "amount": 750.0,
            "bank_reference": "BNK-SA-TEST-001",
        },
    )
    assert pay_res.status_code == 201
    client.post("/api/auth/logout")

    # 2. Log in as Platform Superadmin
    sa_login = client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "SuperAdmin123!"},
    )
    assert sa_login.status_code == 200
    assert sa_login.get_json()["user"]["role"] == "superadmin"

    # 3. Verify Superadmin Overview metrics & revenue separation
    ov_resp = client.get("/api/superadmin/overview")
    assert ov_resp.status_code == 200
    ov = ov_resp.get_json()
    m = ov["metrics"]
    assert m["total_schools"] == 2
    assert m["active_schools"] == 2
    assert m["suspended_schools"] == 0
    assert m["total_students"] == 3
    assert m["total_teachers"] == 1
    assert m["total_admins"] >= 2
    assert m["active_schools_24h"] >= 1
    assert m["active_schools_7d"] >= 1
    # Student fee payment (K750) is tracked in school_fee_collections_zmw, NOT subscription_revenue_zmw
    assert m["subscription_revenue_zmw"] == 0.0
    assert m["school_fee_collections_zmw"] >= 750.0

    # 4. Inspect individual School Detail endpoint (A. Profile, B. Usage, C. Billing, D. Activity Timeline)
    detail_resp = client.get(f"/api/superadmin/schools/{ids['school_a_id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert detail["school"]["name"] == "Lusaka High"
    assert detail["school"]["subdomain"] == "lusakahigh"
    assert len(detail["administrators"]) >= 1
    assert detail["usage"]["students_count"] == 2
    assert detail["usage"]["teachers_count"] == 1
    assert detail["usage"]["classes_count"] == 1
    assert detail["usage"]["terms_count"] == 1
    assert detail["usage"]["tenant_fee_collections_zmw"] >= 750.0
    assert detail["billing"]["current_plan"] == "growth"
    assert detail["activity"]["total"] >= 1
    event_types = {ev["event_type"] for ev in detail["activity"]["items"]}
    assert "fee_payment_confirmed" in event_types or "admin_login" in event_types

    # 5. Payment Integrity Guard: Superadmin cannot upgrade School B to 'enterprise' without a paid Subscription
    unpaid_upgrade = client.post(
        f"/api/superadmin/schools/{ids['school_b_id']}/plan",
        json={"plan": "enterprise", "reason": "Try unpaid upgrade"},
    )
    assert unpaid_upgrade.status_code == 400
    assert "verified subscription payment" in unpaid_upgrade.get_json()["error"].lower()

    # 6. Suspend School A with a recorded audit reason
    susp_resp = client.post(
        f"/api/superadmin/schools/{ids['school_a_id']}/status",
        json={"action": "suspend", "reason": "Compliance review test"},
    )
    assert susp_resp.status_code == 200
    assert susp_resp.get_json()["school"]["is_active"] is False
    assert susp_resp.get_json()["school"]["suspension_reason"] == "Compliance review test"

    # Verify suspension is recorded in the platform activity monitor
    act_resp = client.get(
        f"/api/superadmin/activity?school_id={ids['school_a_id']}&category=school_status"
    )
    assert act_resp.status_code == 200
    act_data = act_resp.get_json()
    assert act_data["total"] >= 1
    assert any("Compliance review test" in item["description"] for item in act_data["items"])

    # 7. Verify suspended school users cannot log in while school data remains intact
    client.post("/api/auth/logout")
    blocked_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )
    assert blocked_login.status_code == 403
    assert blocked_login.get_json().get("school_suspended") is True

    # 8. Superadmin reactivates School A and login works again
    client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "SuperAdmin123!"},
    )
    react_resp = client.post(
        f"/api/superadmin/schools/{ids['school_a_id']}/status",
        json={"action": "activate", "reason": "Compliance review cleared"},
    )
    assert react_resp.status_code == 200
    assert react_resp.get_json()["school"]["is_active"] is True

    client.post("/api/auth/logout")
    restored_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )
    assert restored_login.status_code == 200


def test_admin_phone_validation_and_full_crud_operations(client, seed_two_schools):
    ids = seed_two_schools

    # 1. Login as School A Admin
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )
    assert login_resp.status_code == 200

    # 2. Teacher Phone Normalization & Validation (Accepts spaces, dashes)
    # A. Spaced Zambian local number: "097 712 3456"
    t1_resp = client.post(
        "/api/admin/teachers",
        json={
            "first_name": "Kabwe",
            "last_name": "Phiri",
            "phone": "097 712 3456",
            "email": "kabwe.phiri@school.zm",
            "subject_specialization": "Mathematics",
        },
    )
    assert t1_resp.status_code == 201
    t1_id = t1_resp.get_json()["id"]

    # Verify phone was normalized without spaces
    overview = client.get("/api/admin/overview").get_json()
    created_teacher = next(t for t in overview["teachers"] if t["id"] == t1_id)
    assert created_teacher["phone"] == "0977123456"
    assert created_teacher["email"] == "kabwe.phiri@school.zm"
    assert created_teacher["is_active"] is True

    # B. Spaced international number: "+260 96 123 4567"
    t2_resp = client.post(
        "/api/admin/teachers",
        json={
            "first_name": "Mulenga",
            "last_name": "Mwila",
            "phone": "+260 96 123 4567",
            "subject_specialization": "Physics",
        },
    )
    assert t2_resp.status_code == 201
    t2_id = t2_resp.get_json()["id"]

    # C. Invalid phone number rejection with informative error message
    bad_phone_resp = client.post(
        "/api/admin/teachers",
        json={
            "first_name": "Invalid",
            "last_name": "Number",
            "phone": "12345",
        },
    )
    assert bad_phone_resp.status_code == 400
    assert "Invalid phone number. Please enter the number without spaces" in bad_phone_resp.get_json()["error"]

    # 3. Teacher Update (PUT) & Phone Normalization
    upd_resp = client.put(
        f"/api/admin/teachers/{t1_id}",
        json={
            "first_name": "Kabwe",
            "last_name": "Phiri Senior",
            "phone": "095 888 9999",
            "email": "kabwe.senior@school.zm",
            "subject_specialization": "Advanced Mathematics",
        },
    )
    assert upd_resp.status_code == 200

    # 4. Teacher Status Toggle & Active Check
    toggle_resp = client.post(f"/api/admin/teachers/{t1_id}/toggle-status")
    assert toggle_resp.status_code == 200
    assert toggle_resp.get_json()["is_active"] is False

    # 5. Class CRUD
    class_resp = client.post(
        "/api/admin/classes",
        json={
            "name": "Grade 11B",
            "capacity": 35,
            "grade_level": "Senior Secondary",
            "academic_year": "2026",
            "class_teacher_id": t2_id,
        },
    )
    assert class_resp.status_code == 201
    class_id = class_resp.get_json()["id"]

    # Duplicate class name rejection
    dup_class = client.post(
        "/api/admin/classes",
        json={"name": "Grade 11B", "capacity": 30},
    )
    assert dup_class.status_code == 400

    # Edit class
    edit_class = client.put(
        f"/api/admin/classes/{class_id}",
        json={"name": "Grade 11B Advanced", "capacity": 38, "grade_level": "Grade 11"},
    )
    assert edit_class.status_code == 200

    # 6. Subject CRUD
    subj_resp = client.post(
        "/api/admin/subjects",
        json={
            "name": "Chemistry",
            "code": "CHEM11",
            "description": "General and organic chemistry fundamentals",
        },
    )
    assert subj_resp.status_code == 201
    subj_id = subj_resp.get_json()["id"]

    # Subject status toggle
    subj_toggle = client.post(f"/api/admin/subjects/{subj_id}/toggle-status")
    assert subj_toggle.status_code == 200
    assert subj_toggle.get_json()["is_active"] is False
    # Restore
    client.post(f"/api/admin/subjects/{subj_id}/toggle-status")

    # 7. Academic Term Validation & CRUD
    # Invalid dates: end <= start
    bad_term = client.post(
        "/api/admin/terms",
        json={"name": "Bad Term", "start_date": "2026-08-01", "end_date": "2026-07-01"},
    )
    assert bad_term.status_code == 400
    assert "after start date" in bad_term.get_json()["error"]

    term_resp = client.post(
        "/api/admin/terms",
        json={"name": "Term 3 2026", "start_date": "2026-09-01", "end_date": "2026-12-05"},
    )
    assert term_resp.status_code == 201
    term_id = term_resp.get_json()["id"]

    # 8. Examination CRUD with Date/Time
    exam_resp = client.post(
        "/api/admin/exams",
        json={
            "name": "End of Year Chemistry Exam",
            "term_id": term_id,
            "class_id": class_id,
            "subject_id": subj_id,
            "date": "2026-11-20",
            "start_time": "08:30",
            "end_time": "11:00",
            "venue": "Science Hall B",
            "exam_type": "Final",
        },
    )
    assert exam_resp.status_code == 201
    exam_id = exam_resp.get_json()["id"]

    # Reschedule exam
    resched = client.put(
        f"/api/admin/exams/{exam_id}",
        json={"name": "End of Year Chemistry Exam (Rescheduled)", "start_time": "09:00", "end_time": "11:30"},
    )
    assert resched.status_code == 200

    # 9. Timetable Management & Clash Detection
    # Inactive teacher cannot be assigned:
    inactive_tt_resp = client.post(
        "/api/admin/timetable",
        json={
            "class_id": class_id,
            "subject_id": subj_id,
            "teacher_id": t1_id,  # t1 was deactivated earlier
            "day": "Tuesday",
            "start_time": "08:00",
            "end_time": "09:00",
        },
    )
    assert inactive_tt_resp.status_code == 400
    assert "inactive" in inactive_tt_resp.get_json()["error"]

    # Reactivate t1
    client.post(f"/api/admin/teachers/{t1_id}/toggle-status")

    # Add slot 1 successfully
    tt1_resp = client.post(
        "/api/admin/timetable",
        json={
            "class_id": class_id,
            "subject_id": subj_id,
            "teacher_id": t1_id,
            "day": "Wednesday",
            "start_time": "08:00",
            "end_time": "09:30",
            "room": "Lab 1",
        },
    )
    assert tt1_resp.status_code == 201
    tt1_id = tt1_resp.get_json()["id"]

    # Teacher clash: Teacher t1 cannot teach elsewhere on Wednesday 09:00 to 10:00 (overlaps 08:00 - 09:30)
    clash_resp = client.post(
        "/api/admin/timetable",
        json={
            "class_id": ids["class_a_id"],
            "subject_id": subj_id,
            "teacher_id": t1_id,
            "day": "Wednesday",
            "start_time": "09:00",
            "end_time": "10:00",
        },
    )
    assert clash_resp.status_code == 400
    assert "Teacher schedule clash" in clash_resp.get_json()["error"]

    # Class clash: class_id already has chemistry on Wednesday 08:00 to 09:30
    class_clash_resp = client.post(
        "/api/admin/timetable",
        json={
            "class_id": class_id,
            "subject_id": subj_id,
            "teacher_id": t2_id,
            "day": "Wednesday",
            "start_time": "08:30",
            "end_time": "10:00",
        },
    )
    assert class_clash_resp.status_code == 400
    assert "Class schedule clash" in class_clash_resp.get_json()["error"]

    # Delete timetable slot
    del_tt = client.delete(f"/api/admin/timetable/{tt1_id}")
    assert del_tt.status_code == 200

    # 10. Student Management & Transfer Workflow
    # Register student with spaced phone
    stu_resp = client.post(
        "/api/admin/students",
        json={
            "first_name": "Chipo",
            "last_name": "Banda",
            "admission_no": "ADM-CHIPO-01",
            "gender": "Female",
            "class_id": class_id,
            "phone": "097 999 1122",
            "parent_username": "parent_chipo",
            "parent_phone": "+260 97 444 5566",
        },
    )
    assert stu_resp.status_code == 201
    stu_id = stu_resp.get_json()["student_id"]

    # Transfer student to Class A and change status
    transfer_resp = client.put(
        f"/api/admin/students/{stu_id}",
        json={
            "first_name": "Chipo",
            "last_name": "Banda",
            "admission_no": "ADM-CHIPO-01",
            "class_id": ids["class_a_id"],
            "status": "active",
        },
    )
    assert transfer_resp.status_code == 200

    # Update status to transferred
    status_resp = client.post(
        f"/api/admin/students/{stu_id}/status",
        json={"status": "transferred"},
    )
    assert status_resp.status_code == 200


def test_multiday_exam_periods_and_validation(client, seed_two_schools):
    ids = seed_two_schools

    # Login as Admin of School A
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )
    assert login_resp.status_code == 200

    # 1. Create a Term with fixed start and end dates
    term_resp = client.post(
        "/api/admin/terms",
        json={
            "name": "Term 2 Winter 2026",
            "start_date": "2026-06-01",
            "end_date": "2026-08-31",
        },
    )
    assert term_resp.status_code == 201
    term_id = term_resp.get_json()["id"]

    # 2. Successfully schedule a multi-day exam period
    exam_resp = client.post(
        "/api/admin/exams",
        json={
            "name": "Mid-Year Terminal Assessments",
            "term_id": term_id,
            "start_date": "2026-07-06",
            "end_date": "2026-07-17",
            "start_time": "08:30",
            "end_time": "12:00",
            "venue": "Assembly Hall A",
        },
    )
    assert exam_resp.status_code == 201
    exam_id = exam_resp.get_json()["id"]

    # Verify overview serialization contains start_date and end_date
    overview = client.get("/api/admin/overview").get_json()
    created_exam = next(e for e in overview["exams"] if e["id"] == exam_id)
    assert created_exam["start_date"] == "2026-07-06"
    assert created_exam["end_date"] == "2026-07-17"

    # 3. Validation: end_date < start_date rejected with 400
    bad_dates_resp = client.post(
        "/api/admin/exams",
        json={
            "name": "Invalid Order Exam",
            "term_id": term_id,
            "start_date": "2026-07-20",
            "end_date": "2026-07-15",
        },
    )
    assert bad_dates_resp.status_code == 400
    assert "earlier than start date" in bad_dates_resp.get_json()["error"]

    # 4. Validation: start_date before term start date rejected with 400
    pre_term_resp = client.post(
        "/api/admin/exams",
        json={
            "name": "Pre-Term Exam",
            "term_id": term_id,
            "start_date": "2026-05-15",
            "end_date": "2026-05-20",
        },
    )
    assert pre_term_resp.status_code == 400
    assert "cannot be before term start date" in pre_term_resp.get_json()["error"]

    # 5. Validation: end_date after term end date rejected with 400
    post_term_resp = client.post(
        "/api/admin/exams",
        json={
            "name": "Post-Term Exam",
            "term_id": term_id,
            "start_date": "2026-08-25",
            "end_date": "2026-09-05",
        },
    )
    assert post_term_resp.status_code == 400
    assert "cannot be after term end date" in post_term_resp.get_json()["error"]


def test_teacher_permissions_attendance_once_per_day_and_assignment_attachment(client, app, seed_two_schools):
    ids = seed_two_schools
    import io

    with app.app_context():
        # Setup teacher in School A
        t_user = User(
            school_id=ids["school_a_id"],
            username="teacher_sarah",
            role="teacher",
            is_verified=True,
        )
        t_user.set_password("TeacherPass123")
        db.session.add(t_user)
        db.session.flush()

        teacher = Teacher(
            school_id=ids["school_a_id"],
            user_id=t_user.id,
            first_name="Sarah",
            last_name="Zulu",
            staff_no="TS-0099",
            subject_specialization="Mathematics",
        )
        db.session.add(teacher)
        db.session.flush()

        # Setup subject
        subj = Subject(school_id=ids["school_a_id"], name="Mathematics", code="MATH101")
        db.session.add(subj)
        db.session.flush()
        subject_a_id = subj.id

        # Assign teacher to Class A and Subject A
        t_assign = TeacherAssignment(
            school_id=ids["school_a_id"],
            teacher_id=teacher.id,
            class_id=ids["class_a_id"],
            subject_id=subject_a_id,
        )
        db.session.add(t_assign)

        # Setup student in Class B to test unauthorized attachment access
        class_b = SchoolClass(school_id=ids["school_a_id"], name="Grade 12A", capacity=30)
        db.session.add(class_b)
        db.session.flush()

        b_user = User(
            school_id=ids["school_a_id"],
            username="student_b",
            role="student",
            is_verified=True,
        )
        b_user.set_password("StudentPass123")
        db.session.add(b_user)
        db.session.flush()

        student_b = Student(
            school_id=ids["school_a_id"],
            user_id=b_user.id,
            admission_no="ADM-CLASS-B-01",
            first_name="Brian",
            last_name="Tembo",
            gender="Male",
            class_id=class_b.id,
        )
        db.session.add(student_b)
        db.session.commit()
        class_b_id = class_b.id

    # 1. Login as teacher_sarah
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "teacher_sarah", "password": "TeacherPass123", "school_subdomain": "lusakahigh"},
    )
    assert login_resp.status_code == 200

    # 2. Teacher overview returns only assigned classes
    t_ov = client.get("/api/teacher/overview").get_json()
    assigned_class_ids = [c["id"] for c in t_ov["classes"]]
    assert ids["class_a_id"] in assigned_class_ids
    assert class_b_id not in assigned_class_ids

    # 3. Attendance once-per-day enforcement
    today_str = "2026-06-15"
    # First roll call
    att1 = client.post(
        f"/api/teacher/attendance/{ids['class_a_id']}",
        json={
            "date": today_str,
            "records": {str(ids["stu_a1_id"]): "Present"},
            "allow_edit": False,
        },
    )
    assert att1.status_code == 200

    # Second roll call for same date without allow_edit rejected with 409
    att2_dup = client.post(
        f"/api/teacher/attendance/{ids['class_a_id']}",
        json={
            "date": today_str,
            "records": {str(ids["stu_a1_id"]): "Absent"},
            "allow_edit": False,
        },
    )
    assert att2_dup.status_code == 409
    assert att2_dup.get_json()["already_recorded"] is True

    # Roll call with allow_edit=True succeeds
    att3_edit = client.post(
        f"/api/teacher/attendance/{ids['class_a_id']}",
        json={
            "date": today_str,
            "records": {str(ids["stu_a1_id"]): "Absent"},
            "allow_edit": True,
        },
    )
    assert att3_edit.status_code == 200

    # 4. Teacher unauthorized class rejection (403 for unassigned Class B)
    unauth_att = client.post(
        f"/api/teacher/attendance/{class_b_id}",
        json={"date": today_str, "records": {}},
    )
    assert unauth_att.status_code == 403

    # 5. Teacher creates assignment with attachment file for assigned Class A
    file_content = b"%PDF-1.4 Assignment Content for Class A"
    assign_resp = client.post(
        "/api/teacher/assignments",
        data={
            "title": "Algebra Worksheet 1",
            "description": "Complete problems 1 to 20.",
            "class_id": str(ids["class_a_id"]),
            "subject_id": str(subject_a_id),
            "assignment_date": "2026-06-16",
            "due_date": "2026-06-25",
            "file": (io.BytesIO(file_content), "algebra_worksheet_1.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert assign_resp.status_code == 201
    assign_id = assign_resp.get_json()["id"]

    # 6. Student in Class A downloads attachment successfully
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"username": "LH001", "password": "student123", "school_subdomain": "lusakahigh"},
    )
    dl_resp = client.get(f"/api/assignments/{assign_id}/attachment")
    assert dl_resp.status_code == 200
    assert dl_resp.data == file_content
    dl_resp.close()

    # 7. Student in Class B is blocked with 403 Forbidden
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"username": "student_b", "password": "StudentPass123", "school_subdomain": "lusakahigh"},
    )
    dl_blocked = client.get(f"/api/assignments/{assign_id}/attachment")
    assert dl_blocked.status_code == 403
    dl_blocked.close()


def test_parent_provisioning_linking_and_portal_access(client, app, seed_two_schools):
    ids = seed_two_schools

    # 1. Admin login
    client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminPass123", "school_subdomain": "lusakahigh"},
    )

    # 2. Admin provisions parent account
    create_parent_resp = client.post(
        "/api/admin/parents",
        json={
            "first_name": "Loveness",
            "last_name": "Phiri",
            "phone": "+260 97 123 9999",
            "email": "loveness.phiri@example.com",
            "username": "loveness_p",
            "password": "ParentSecure123",
            "student_ids": [ids["stu_a1_id"]],
        },
    )
    assert create_parent_resp.status_code == 201
    parent_id = create_parent_resp.get_json()["parent_id"]

    # 3. List parents endpoint verifies parent created and child linked
    parents_list = client.get("/api/admin/parents").get_json()["parents"]
    created_parent = next(p for p in parents_list if p["id"] == parent_id)
    assert created_parent["username"] == "loveness_p"
    assert created_parent["phone"] == "0971239999"
    assert len(created_parent["linked_students"]) == 1
    assert created_parent["linked_students"][0]["id"] == ids["stu_a1_id"]

    # 4. Parent logs in through shared login endpoint
    client.post("/api/auth/logout")
    p_login = client.post(
        "/api/auth/login",
        json={"username": "loveness_p", "password": "ParentSecure123", "school_subdomain": "lusakahigh"},
    )
    assert p_login.status_code == 200
    assert p_login.get_json()["user"]["role"] == "parent"

    # 5. Parent overview contains child profile, attendance, results, and fee balances
    p_ov = client.get("/api/parent/overview").get_json()
    assert len(p_ov["children"]) == 1
    child = p_ov["children"][0]
    assert child["id"] == ids["stu_a1_id"]
    assert "fee_balances" in child
    assert "results" in child
    assert "attendance" in child
    assert "assignments" in child
    assert "exams" in child
    assert "assignments" in child
    assert "exams" in child







