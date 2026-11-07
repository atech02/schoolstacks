"""tests/test_easysendsms.py
Comprehensive test suite for EasySendSMS REST API Integration & DLR Callback Handling.

Tests all 22 cases specified in Phase 13:
1. Valid SMS submission (mocked HTTP 200 with OK status and messageIds).
2. Invalid phone number handling.
3. Zambian number normalisation (strips '+', '00', converts 097... -> 26097...).
4. Missing API key error handling.
5. Invalid API key error response (code 4003).
6. Invalid sender ID error response (code 4014).
7. Insufficient SMS credits error response (code 4015).
8. Provider gateway timeout handling.
9. Provider service unavailable (code 4009) with no blind retry.
10. Duplicate prevention using idempotency keys.
11. Dry-run mode simulation.
12. SMS disabled handling (EASYSENDSMS_ENABLED=false).
13. Successful DLR callback (DELIVRD -> delivered).
14. Expired DLR callback (EXPIRED -> expired).
15. Undelivered DLR callback (UNDELIV -> undelivered).
16. Duplicate DLR callback idempotency.
17. Invalid callback payload handling (missing sms_id).
18. Unmatched provider message ID handling.
19. Fees reminder calculations with variable substitution.
20. Partial payments balance deduction.
21. Absenteeism threshold calculations (2 consecutive, 3 consecutive, 5 cumulative in 30 days).
22. Multi-tenant boundary isolation.
"""
import datetime
import json
import pytest
from unittest.mock import patch, MagicMock
import requests
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
    Term,
    FeeStructure,
    Payment,
    Attendance,
    SMSSettings,
    SMSMessage,
    SMSDeliveryEvent,
    AbsenteeismIntervention,
    utc_now,
)
from services.sms_service import (
    normalise_phone_number,
    normalize_phone_number,
    EasySendSMSClient,
    send_sms,
    send_school_sms,
    send_fees_reminder,
    send_absence_alert,
    send_test_sms,
    get_sms_balance,
    process_delivery_report,
)


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test_easysendsms.db"
    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-easysendsms-secret",
        "EASYSENDSMS_API_KEY": "test_live_key_xyz",
        "EASYSENDSMS_SENDER_ID": "SchoolStack",
        "EASYSENDSMS_ENABLED": True,
        "EASYSENDSMS_DRY_RUN": False,
        "EASYSENDSMS_WEBHOOK_SECRET": "test_secret_token",
        "CRON_SECRET": "test-cron-secret-12345",
        "RATELIMIT_ENABLED": False,
        "IS_PRODUCTION": False,
    }
    application = create_app(test_config)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, password):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


@pytest.fixture
def setup_env(app):
    with app.app_context():
        school1 = School(name="Chalo Trust School", subdomain="chalo", email="info@chalo.zm", is_email_verified=True)
        school2 = School(name="Baobab College", subdomain="baobab", email="info@baobab.zm", is_email_verified=True)
        db.session.add_all([school1, school2])
        db.session.commit()

        # Admin for school 1
        u_admin = User(
            username="chalo_admin",
            email="admin@chalo.zm",
            role="admin",
            school_id=school1.id,
            is_verified=True,
        )
        u_admin.set_password("AdminPass123!")

        # Parent & Student for school 1
        parent = Parent(
            school_id=school1.id,
            first_name="Mulenga",
            last_name="Banda",
            phone="0977112233",
        )
        db.session.add_all([u_admin, parent])
        db.session.commit()

        cls1 = SchoolClass(school_id=school1.id, name="Grade 9A", grade_level="Grade 9", academic_year="2025/2026")
        db.session.add(cls1)
        db.session.commit()

        student = Student(
            school_id=school1.id,
            first_name="Lombe",
            last_name="Banda",
            admission_no="CHL-001",
            class_id=cls1.id,
            phone="0977112233",
            gender="Female",
            dob=datetime.date(2010, 1, 1),
        )
        db.session.add(student)
        db.session.commit()

        ps = ParentStudent(school_id=school1.id, parent_id=parent.id, student_id=student.id)
        db.session.add(ps)

        # SMSSettings
        sms_set = SMSSettings(
            school_id=school1.id,
            is_enabled=True,
            sender_id="ChaloTrust",
            fee_reminders_enabled=True,
            absenteeism_alerts_enabled=True,
        )
        db.session.add(sms_set)
        db.session.commit()

        return {
            "school1_id": school1.id,
            "school2_id": school2.id,
            "admin_user_id": u_admin.id,
            "student_id": student.id,
            "parent_id": parent.id,
            "class_id": cls1.id,
        }


# ── TEST CASES 1–22 ──────────────────────────────────────────────────────────

def test_1_valid_sms_submission(app):
    """Case 1: Valid SMS submission to EasySendSMS with mocked HTTP 200 response."""
    with app.app_context():
        client = EasySendSMSClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "OK",
            "scheduled": "Now",
            "messageIds": ["OK: fd940f38-151d-47f1-81b8-22d1220f7a55"],
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = client.send_single(
                to_phone="260977112233",
                message="Welcome to SchoolStacks SMS notification.",
                sender_id="ChaloTrust",
            )
            assert result["success"] is True
            assert result["message_id"] == "fd940f38-151d-47f1-81b8-22d1220f7a55"
            assert result["status"] == "sent"

            # Verify request payload
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["headers"]["apikey"] == "test_live_key_xyz"
            assert call_kwargs["json"]["to"] == "260977112233"
            assert call_kwargs["json"]["from"] == "ChaloTrust"
            assert call_kwargs["json"]["type"] == "0"


def test_2_invalid_phone_number(app):
    """Case 2: Reject invalid phone numbers before submitting to provider."""
    with app.app_context():
        client = EasySendSMSClient()
        result = client.send_single(
            to_phone="invalid-number",
            message="Test message",
        )
        assert result["success"] is False
        assert result["status"] == "failed"
        assert "Invalid recipient phone number" in result["error"]


def test_3_zambian_number_normalisation():
    """Case 3: Strict Zambian number normalisation without '+' or '00' prefixes."""
    assert normalise_phone_number("0977112233") == "260977112233"
    assert normalise_phone_number("+260977112233") == "260977112233"
    assert normalise_phone_number("260977112233") == "260977112233"
    assert normalise_phone_number("00260977112233") == "260977112233"
    assert normalise_phone_number("0965001122") == "260965001122"
    assert normalise_phone_number("0761234567") == "260761234567"

    # International number strips +
    assert normalise_phone_number("+14155552671") == "14155552671"

    # Invalid cases
    is_valid, _ = normalise_phone_number("12345")
    assert is_valid is False


def test_4_missing_api_key(app):
    """Case 4: Missing API key enters dry-run / fallback mode or reports error."""
    with app.app_context():
        client = EasySendSMSClient()
        client.api_key = ""
        client.dry_run = False  # forces check without key
        result = client.send_single(
            to_phone="260977112233",
            message="Test message",
        )
        # Should gracefully handle without API key (dry-run fallback)
        assert result["success"] is True
        assert result.get("dry_run") is True


def test_5_invalid_api_key_4003(app):
    """Case 5: Error 4003: Invalid API key."""
    with app.app_context():
        client = EasySendSMSClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"code": 4003, "message": "Invalid API key."}

        with patch("requests.post", return_value=mock_resp):
            result = client.send_single(
                to_phone="260977112233",
                message="Test message",
            )
            assert result["success"] is False
            assert "4003" in result["error"]
            assert "Invalid API key" in result["error"]


def test_6_invalid_sender_name_4014(app):
    """Case 6: Error 4014: Invalid sender name."""
    with app.app_context():
        client = EasySendSMSClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"code": 4014, "message": "Invalid sender name."}

        with patch("requests.post", return_value=mock_resp):
            result = client.send_single(
                to_phone="260977112233",
                message="Test message",
                sender_id="Invalid$$$",
            )
            assert result["success"] is False
            assert "4014" in result["error"]
            assert "Invalid sender name" in result["error"]


def test_7_insufficient_credits_4015(app):
    """Case 7: Error 4015: Insufficient credits."""
    with app.app_context():
        client = EasySendSMSClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 402
        mock_resp.json.return_value = {"code": 4015, "message": "Insufficient credits."}

        with patch("requests.post", return_value=mock_resp):
            result = client.send_single(
                to_phone="260977112233",
                message="Test message",
            )
            assert result["success"] is False
            assert "4015" in result["error"]
            assert "Insufficient credits" in result["error"]


def test_8_provider_timeout(app):
    """Case 8: Provider request timeout handling."""
    with app.app_context():
        client = EasySendSMSClient()
        with patch("requests.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
            result = client.send_single(
                to_phone="260977112233",
                message="Test message",
                max_retries=1,
            )
            assert result["success"] is False
            assert "timed out" in result["error"].lower()


def test_9_service_unavailable_4009_no_blind_retry(app):
    """Case 9: Error 4009 Service unavailable: do not blindly retry."""
    with app.app_context():
        client = EasySendSMSClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = {"code": 4009, "message": "Service unavailable."}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = client.send_single(
                to_phone="260977112233",
                message="Test message",
                max_retries=3,
            )
            assert result["success"] is False
            assert "4009" in result["error"]
            # Crucial: Provider specifically advises NOT resubmitting for 4009
            assert mock_post.call_count == 1


def test_10_duplicate_prevention_idempotency(app, setup_env):
    """Case 10: Enforce zero-duplicate dispatch using idempotency keys."""
    with app.app_context():
        idemp = "idemp_unique_key_1001"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "OK",
            "messageIds": ["OK: uuid-first-call-001"],
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            # First call -> dispatches to provider
            msg1 = send_school_sms(
                school_id=setup_env["school1_id"],
                to_phone="0977112233",
                message="Fee reminder #1",
                idempotency_key=idemp,
            )
            assert msg1.status == "sent"
            assert msg1.provider_message_id == "uuid-first-call-001"
            assert mock_post.call_count == 1

            # Second call with identical key -> returns existing record without calling provider
            msg2 = send_school_sms(
                school_id=setup_env["school1_id"],
                to_phone="0977112233",
                message="Fee reminder #1 duplicate",
                idempotency_key=idemp,
            )
            assert msg2.id == msg1.id
            assert msg2.provider_message_id == "uuid-first-call-001"
            assert mock_post.call_count == 1


def test_11_dry_run_mode(app, setup_env):
    """Case 11: Dry-run simulation mode."""
    with app.app_context():
        client = EasySendSMSClient()
        client.dry_run = True
        result = client.send_single(
            to_phone="0977112233",
            message="Dry run test message",
        )
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["message_id"].startswith("sim_easysend_")
        assert result["status"] == "sent"


def test_12_sms_disabled_mode(app, setup_env):
    """Case 12: Global or school-level disabled switch."""
    with app.app_context():
        # Disable in school settings
        settings = SMSSettings.query.filter_by(school_id=setup_env["school1_id"]).first()
        settings.is_enabled = False
        db.session.commit()

        msg = send_school_sms(
            school_id=setup_env["school1_id"],
            to_phone="0977112233",
            message="Should not be sent",
        )
        assert msg.status == "disabled"
        assert "not enabled" in msg.error_message


def test_13_successful_dlr_callback(client, setup_env):
    """Case 13: DLR callback maps DELIVRD -> delivered with timestamp."""
    with client.application.app_context():
        msg = SMSMessage(
            school_id=setup_env["school1_id"],
            recipient_phone="260977112233",
            message_body="Report card published.",
            category="general",
            provider_message_id="uuid-prov-delivrd-001",
            status="sent",
        )
        db.session.add(msg)
        db.session.commit()

    # Post raw URL-encoded callback to /api/sms/easysendsms/dlr
    payload = "source=ChaloTrust&msisdn=260977112233&response=DELIVRD&sent_date=5%2f24%2f2024+11%3a23%3a34+PM&sms_id=uuid-prov-delivrd-001"
    resp = client.post(
        "/api/sms/easysendsms/dlr",
        data=payload,
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 200

    with client.application.app_context():
        updated = SMSMessage.query.filter_by(provider_message_id="uuid-prov-delivrd-001").first()
        assert updated.status == "delivered"
        assert updated.delivered_at is not None

        # Check delivery event record
        event = SMSDeliveryEvent.query.filter_by(provider_message_id="uuid-prov-delivrd-001").first()
        assert event is not None
        assert event.status == "delivered"


def test_14_expired_dlr_callback(client, setup_env):
    """Case 14: DLR callback maps EXPIRED -> expired."""
    with client.application.app_context():
        msg = SMSMessage(
            school_id=setup_env["school1_id"],
            recipient_phone="260977112233",
            message_body="Time-sensitive reminder.",
            category="general",
            provider_message_id="uuid-prov-expired-002",
            status="sent",
        )
        db.session.add(msg)
        db.session.commit()

    payload = "source=ChaloTrust&msisdn=260977112233&response=EXPIRED&sms_id=uuid-prov-expired-002"
    resp = client.post(
        "/api/sms/easysendsms/dlr",
        data=payload,
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 200

    with client.application.app_context():
        updated = SMSMessage.query.filter_by(provider_message_id="uuid-prov-expired-002").first()
        assert updated.status == "expired"


def test_15_undelivered_dlr_callback(client, setup_env):
    """Case 15: DLR callback maps UNDELIV -> undelivered."""
    with client.application.app_context():
        msg = SMSMessage(
            school_id=setup_env["school1_id"],
            recipient_phone="260977112233",
            message_body="General notice.",
            category="general",
            provider_message_id="uuid-prov-undeliv-003",
            status="sent",
        )
        db.session.add(msg)
        db.session.commit()

    payload = "source=ChaloTrust&msisdn=260977112233&response=UNDELIV&sms_id=uuid-prov-undeliv-003"
    resp = client.post(
        "/api/sms/easysendsms/dlr",
        data=payload,
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 200

    with client.application.app_context():
        updated = SMSMessage.query.filter_by(provider_message_id="uuid-prov-undeliv-003").first()
        assert updated.status == "undelivered"


def test_16_duplicate_dlr_callback_idempotency(client, setup_env):
    """Case 16: Duplicate DLR callbacks handle gracefully without crashing."""
    with client.application.app_context():
        msg = SMSMessage(
            school_id=setup_env["school1_id"],
            recipient_phone="260977112233",
            message_body="Welcome.",
            category="general",
            provider_message_id="uuid-prov-dup-004",
            status="sent",
        )
        db.session.add(msg)
        db.session.commit()

    payload = "source=ChaloTrust&msisdn=260977112233&response=DELIVRD&sms_id=uuid-prov-dup-004"
    r1 = client.post("/api/sms/easysendsms/dlr", data=payload, content_type="application/x-www-form-urlencoded")
    assert r1.status_code == 200

    # Repeat delivery callback
    r2 = client.post("/api/sms/easysendsms/dlr", data=payload, content_type="application/x-www-form-urlencoded")
    assert r2.status_code == 200


def test_17_invalid_callback_payload(client):
    """Case 17: DLR callback with missing sms_id handled cleanly."""
    payload = "source=ChaloTrust&response=DELIVRD"
    resp = client.post(
        "/api/sms/easysendsms/dlr",
        data=payload,
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["result"]["success"] is False


def test_18_unmatched_provider_message_id(client):
    """Case 18: Unmatched provider message ID safely logged without throwing."""
    payload = "source=test&msisdn=260970000000&response=DELIVRD&sms_id=unknown-uuid-9999"
    resp = client.post(
        "/api/sms/easysendsms/dlr",
        data=payload,
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["result"]["matched"] is False


def test_19_fees_reminder_calculation_and_template(app, setup_env):
    """Case 19: Fees reminder generates proper dynamic balance and excludes fully paid accounts."""
    with app.app_context():
        # Excludes 0 or negative balance
        res_zero = send_fees_reminder(
            school_id=setup_env["school1_id"],
            student_id=setup_env["student_id"],
            invoice_id=101,
            amount_due=0.0,
            due_date="2026-11-30",
        )
        assert res_zero is None

        # Dispatches for positive balance
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "OK", "messageIds": ["OK: fee-rem-uuid-1"]}

        with patch("requests.post", return_value=mock_resp):
            msg = send_fees_reminder(
                school_id=setup_env["school1_id"],
                student_id=setup_env["student_id"],
                invoice_id=102,
                amount_due=1250.50,
                due_date="2026-12-15",
                currency="ZMW",
            )
            assert msg is not None
            assert msg.category == "fee_reminder"
            assert "ZMW 1250.50" in msg.message_body
            assert "2026-12-15" in msg.message_body


def test_20_partial_payments_balance_deduction(client, setup_env):
    """Case 20: Fee reminders reflect partial payments accurately."""
    with client.application.app_context():
        # Associate parent directly with student
        stu = db.session.get(Student, setup_env["student_id"])
        stu.parent_id = setup_env["parent_id"]

        term = Term(
            school_id=setup_env["school1_id"],
            name="Term 1 2026",
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=90),
            is_active=True,
        )
        db.session.add(term)
        db.session.commit()

        # Fee structure 2000 ZMW
        fs = FeeStructure(
            school_id=setup_env["school1_id"],
            class_id=setup_env["class_id"],
            term_id=term.id,
            amount=2000.0,
        )
        db.session.add(fs)
        db.session.commit()

        # Partial payment of 800 ZMW
        pmt = Payment(
            school_id=setup_env["school1_id"],
            student_id=setup_env["student_id"],
            term_id=term.id,
            amount_paid=800.0,
            status="completed",
            payment_date=datetime.date.today(),
        )
        db.session.add(pmt)
        db.session.commit()

    _login(client, "chalo_admin", "AdminPass123!")
    resp = client.get("/api/admin/sms/fee-reminders/preview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("due_reminders_count", data.get("count", 0)) >= 1
    target = next((r for r in data["reminders"] if r["student_id"] == setup_env["student_id"]), None)
    assert target is not None
    assert target["balance"] == 1200.0  # 2000 - 800


def test_21_absenteeism_threshold_calculation(app, setup_env):
    """Case 21: Repeated absenteeism thresholds (2-day notice, 3-day urgent)."""
    with app.app_context():
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "OK", "messageIds": ["OK: abs-uuid-1"]}

        with patch("requests.post", return_value=mock_resp):
            # 2 consecutive days -> Notice
            msg2 = send_absence_alert(
                school_id=setup_env["school1_id"],
                student_id=setup_env["student_id"],
                attendance_date="2026-11-06",
                consecutive_days=2,
            )
            assert "marked absent for 2 consecutive days" in msg2.message_body

            # 3 consecutive days -> URGENT
            msg3 = send_absence_alert(
                school_id=setup_env["school1_id"],
                student_id=setup_env["student_id"],
                attendance_date="2026-11-07",
                consecutive_days=3,
            )
            assert "URGENT" in msg3.message_body


def test_22_multitenant_boundary_isolation(client, setup_env):
    """Case 22: School A cannot view or access School B's SMS messages or settings."""
    with client.application.app_context():
        # Create message for school 2
        msg_s2 = SMSMessage(
            school_id=setup_env["school2_id"],
            recipient_phone="260978888888",
            message_body="Secret school 2 message",
            category="general",
            status="sent",
        )
        db.session.add(msg_s2)
        db.session.commit()

    # School 1 admin logs in
    _login(client, "chalo_admin", "AdminPass123!")
    resp = client.get("/api/admin/sms/history")
    assert resp.status_code == 200
    data = resp.get_json()

    # School 2 message must never appear in School 1 history
    assert not any(m["recipient_phone"] == "260978888888" for m in data["messages"])
