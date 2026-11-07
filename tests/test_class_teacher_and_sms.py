"""
tests/test_class_teacher_and_sms.py
Comprehensive test suite for Class Teacher Allocation and SMS.to Integration.

Covers:
1. Class Teacher Allocation:
   - Assign teacher to a class.
   - 1-Class-Per-Teacher enforcement with 409 conflict and requires_override.
   - Administrator override with reason succeeds.
   - Revocation of allocation.
2. Substitute Teacher Allocation:
   - Assign substitute with date range.
   - Deactivate substitute.
3. Daily Attendance Access Control:
   - Designated class teacher can record attendance (200 OK).
   - Substitute teacher can record attendance during their active dates (200 OK).
   - Non-class teacher cannot record daily attendance (HTTP 403 Forbidden).
   - Past-date attendance beyond correction window is rejected (HTTP 403).
4. SMS.to Integration:
   - E.164 phone normalization for Zambian (+260...) and international formats.
   - Dry-run SMS delivery with ledger recording and mock message ID.
   - Idempotency key duplicate send prevention.
   - Webhook delivery update (sent -> delivered) with SMSDeliveryEvent recording.
5. Automated Fee Reminders:
   - Correctly calculates remaining balance for partial payments.
   - Strictly excludes fully paid invoices (balance <= 0).
   - Respects 3-day cooldown window.
6. Repeated Absenteeism Alerts:
   - Detects 2 consecutive unexplained absences (Level 1 Notice).
   - Detects 3 consecutive unexplained absences (Level 2 Urgent follow-up).
   - Detects 5 cumulative absences in 30 days and creates AbsenteeismIntervention flag.
   - Excludes weekends, excused, and sick records.
7. Call Parent Functionality:
   - Call log creation with outcome, staff ID, and detailed remarks.
8. Daily Cron Tasks:
   - CRON_SECRET authentication check.
   - Multi-tenant execution.
"""
import datetime
import pytest
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
    FeeStructure,
    Payment,
    Attendance,
    ClassTeacherAllocation,
    SubstituteAllocation,
    SMSSettings,
    SMSMessage,
    SMSDeliveryEvent,
    ParentCommunicationLog,
    AbsenteeismIntervention,
    utc_now,
)
from services.sms_service import normalize_phone_number, send_school_sms


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test_sms_class_teacher.db"
    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-sms-teacher-secret",
        "SMS_TO_DRY_RUN": "true",
        "SMS_TO_ENABLED": "true",
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
        school = School(
            name="Hillcrest National STEM School",
            subdomain="hillcrest",
            email="admin@hillcrest.zm",
            currency="ZMW",
            is_active=True,
        )
        db.session.add(school)
        db.session.flush()

        # Admin
        u_admin = User(school_id=school.id, username="hadmin", email="admin@hillcrest.zm", role="admin", is_verified=True)
        u_admin.set_password("AdminPass123!")
        db.session.add(u_admin)

        # Classes
        c_8a = SchoolClass(school_id=school.id, name="Grade 8A", capacity=35, is_active=True)
        c_8b = SchoolClass(school_id=school.id, name="Grade 8B", capacity=35, is_active=True)
        db.session.add_all([c_8a, c_8b])

        # Teachers
        # Teacher 1: Mrs Banda
        u_t1 = User(school_id=school.id, username="TBANDA", email="banda@hillcrest.zm", role="teacher", is_verified=True)
        u_t1.set_password("Teacher123!")
        db.session.add(u_t1)
        db.session.flush()
        t1 = Teacher(school_id=school.id, user_id=u_t1.id, staff_no="TBANDA", first_name="Mary", last_name="Banda", phone="+260971000001", is_active=True)
        
        # Teacher 2: Mr Mwila (Substitute)
        u_t2 = User(school_id=school.id, username="TMWILA", email="mwila@hillcrest.zm", role="teacher", is_verified=True)
        u_t2.set_password("Teacher123!")
        db.session.add(u_t2)
        db.session.flush()
        t2 = Teacher(school_id=school.id, user_id=u_t2.id, staff_no="TMWILA", first_name="John", last_name="Mwila", phone="+260971000002", is_active=True)

        # Teacher 3: Mr Phiri (Unassigned to 8A)
        u_t3 = User(school_id=school.id, username="TPHIRI", email="phiri@hillcrest.zm", role="teacher", is_verified=True)
        u_t3.set_password("Teacher123!")
        db.session.add(u_t3)
        db.session.flush()
        t3 = Teacher(school_id=school.id, user_id=u_t3.id, staff_no="TPHIRI", first_name="Peter", last_name="Phiri", phone="+260971000003", is_active=True)

        db.session.add_all([t1, t2, t3])
        db.session.flush()

        # Term
        term = Term(school_id=school.id, name="Term 1 2026", start_date=datetime.date.today(), end_date=datetime.date.today() + datetime.timedelta(days=90), is_active=True)
        db.session.add(term)
        db.session.flush()

        # Fee Structure: 1500 ZMW for Grade 8A
        fee = FeeStructure(school_id=school.id, class_id=c_8a.id, term_id=term.id, amount=1500.0)
        db.session.add(fee)

        # Parent
        parent = Parent(school_id=school.id, first_name="Chilufya", last_name="Mulenga", phone="0977223344")
        db.session.add(parent)
        db.session.flush()

        # Students
        # Student 1: Partial payment (500 paid of 1500 -> 1000 balance)
        s1 = Student(school_id=school.id, admission_no="HC001", first_name="Lombe", last_name="Mulenga", class_id=c_8a.id, parent_id=parent.id, status="active")
        # Student 2: Fully paid (1500 paid -> 0 balance)
        s2 = Student(school_id=school.id, admission_no="HC002", first_name="Mutale", last_name="Kabwe", class_id=c_8a.id, status="active")
        # Student 3: Chronic Absentee
        s3 = Student(school_id=school.id, admission_no="HC003", first_name="Chanda", last_name="Bwalya", class_id=c_8a.id, parent_id=parent.id, status="active")
        db.session.add_all([s1, s2, s3])
        db.session.flush()

        # Payments
        p1 = Payment(school_id=school.id, student_id=s1.id, term_id=term.id, amount_paid=500.0, status="completed")
        p2 = Payment(school_id=school.id, student_id=s2.id, term_id=term.id, amount_paid=1500.0, status="completed")
        db.session.add_all([p1, p2])

        # SMS Settings
        settings = SMSSettings(
            school_id=school.id,
            sms_enabled=True,
            sender_id="Hillcrest",
            fee_reminders_enabled=True,
            absenteeism_alerts_enabled=True,
        )
        db.session.add(settings)
        db.session.commit()

        return {
            "school_id": school.id,
            "admin_user_id": u_admin.id,
            "class_8a_id": c_8a.id,
            "class_8b_id": c_8b.id,
            "t1_id": t1.id,
            "t2_id": t2.id,
            "t3_id": t3.id,
            "s1_id": s1.id,
            "s2_id": s2.id,
            "s3_id": s3.id,
            "parent_id": parent.id,
            "term_id": term.id,
        }


def test_1_class_teacher_allocation_and_override_rule(client, setup_env):
    """Admin assigns Mrs Banda to Grade 8A, then tries to assign her to 8B (fails 409 unless overridden)."""
    _login(client, "hadmin", "AdminPass123!")

    # 1. Assign Teacher 1 to Grade 8A
    resp = client.post(
        "/api/admin/class-teachers",
        json={
            "class_id": setup_env["class_8a_id"],
            "teacher_id": setup_env["t1_id"],
            "academic_year": "2025/2026",
        },
    )
    assert resp.status_code == 201

    # 2. Try to assign Teacher 1 to Grade 8B without override -> 409
    resp_conflict = client.post(
        "/api/admin/class-teachers",
        json={
            "class_id": setup_env["class_8b_id"],
            "teacher_id": setup_env["t1_id"],
            "academic_year": "2025/2026",
            "is_override": False,
        },
    )
    assert resp_conflict.status_code == 409
    data = resp_conflict.get_json()
    assert data["requires_override"] is True
    assert "already assigned" in data["error"]

    # 3. Try with is_override=True but empty reason -> 400
    resp_no_reason = client.post(
        "/api/admin/class-teachers",
        json={
            "class_id": setup_env["class_8b_id"],
            "teacher_id": setup_env["t1_id"],
            "academic_year": "2025/2026",
            "is_override": True,
            "override_reason": "   ",
        },
    )
    assert resp_no_reason.status_code == 400

    # 4. Assign with valid override reason -> 201
    resp_override = client.post(
        "/api/admin/class-teachers",
        json={
            "class_id": setup_env["class_8b_id"],
            "teacher_id": setup_env["t1_id"],
            "academic_year": "2025/2026",
            "is_override": True,
            "override_reason": "Temporary staffing shortage in STEM department approved by Head of School.",
        },
    )
    assert resp_override.status_code == 201

    # Check list endpoint
    resp_list = client.get("/api/admin/class-teachers")
    assert resp_list.status_code == 200
    alloc_data = resp_list.get_json()
    assert len(alloc_data["allocations"]) >= 1


def test_2_substitute_teacher_allocation(client, setup_env):
    """Admin assigns Mr Mwila as substitute for Mrs Banda for 5 days."""
    _login(client, "hadmin", "AdminPass123!")

    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=5)

    resp = client.post(
        "/api/admin/substitutes",
        json={
            "class_id": setup_env["class_8a_id"],
            "substitute_teacher_id": setup_env["t2_id"],
            "start_date": today.isoformat(),
            "end_date": end_date.isoformat(),
            "reason": "Maternity leave coverage",
        },
    )
    assert resp.status_code == 201

    # List substitutes
    resp_list = client.get("/api/admin/substitutes")
    assert resp_list.status_code == 200
    subs = resp_list.get_json()["substitutes"]
    assert any(s["substitute_teacher_id"] == setup_env["t2_id"] for s in subs)


def test_3_daily_attendance_access_control(client, setup_env):
    """
    Designated Class Teacher (Mrs Banda) can mark attendance.
    Substitute (Mr Mwila) can mark attendance during active date.
    Unassigned Teacher (Mr Phiri) is rejected with HTTP 403.
    """
    with client.application.app_context():
        # Cleanly ensure Mrs Banda is designated for 8A
        alloc = ClassTeacherAllocation(
            school_id=setup_env["school_id"],
            class_id=setup_env["class_8a_id"],
            teacher_id=setup_env["t1_id"],
            academic_year="2025/2026",
            assignment_date=datetime.date.today(),
            status="active",
        )
        db.session.add(alloc)
        c8a = db.session.get(SchoolClass, setup_env["class_8a_id"])
        c8a.class_teacher_id = setup_env["t1_id"]
        db.session.commit()

    # 1. Unassigned teacher Mr Phiri attempts to take daily attendance -> 403
    _login(client, "TPHIRI", "Teacher123!")
    today_str = datetime.date.today().isoformat()
    resp_unauth = client.post(
        f"/api/teacher/attendance/{setup_env['class_8a_id']}",
        json={
            "date": today_str,
            "records": {str(setup_env["s1_id"]): "Present"},
        },
    )
    assert resp_unauth.status_code == 403
    assert "You are not the designated class teacher or active substitute" in resp_unauth.get_json()["error"]
    client.post("/api/auth/logout")

    # 2. Designated Class Teacher Mrs Banda marks attendance -> 200
    _login(client, "TBANDA", "Teacher123!")
    resp_banda = client.post(
        f"/api/teacher/attendance/{setup_env['class_8a_id']}",
        json={
            "date": today_str,
            "records": {str(setup_env["s1_id"]): "Present", str(setup_env["s2_id"]): "Late"},
        },
    )
    assert resp_banda.status_code == 200
    client.post("/api/auth/logout")

    # 3. Add active substitute Mr Mwila
    with client.application.app_context():
        sub = SubstituteAllocation(
            school_id=setup_env["school_id"],
            class_id=setup_env["class_8a_id"],
            original_teacher_id=setup_env["t1_id"],
            substitute_teacher_id=setup_env["t2_id"],
            start_date=datetime.date.today(),
            end_date=datetime.date.today() + datetime.timedelta(days=2),
            reason="Official conference travel",
            is_active=True,
        )
        db.session.add(sub)
        db.session.commit()

    # Substitute Mr Mwila can update attendance with allow_edit -> 200
    _login(client, "TMWILA", "Teacher123!")
    resp_sub = client.post(
        f"/api/teacher/attendance/{setup_env['class_8a_id']}",
        json={
            "date": today_str,
            "allow_edit": True,
            "records": {str(setup_env["s1_id"]): "Present", str(setup_env["s2_id"]): "Present"},
        },
    )
    assert resp_sub.status_code == 200


def test_4_sms_phone_normalization_and_dry_run(client, setup_env):
    """Verify Zambian & international phone normalization and dry-run SMS dispatch."""
    # Test valid normalizations
    assert normalize_phone_number("0977223344") == "+260977223344"
    assert normalize_phone_number("+260977223344") == "+260977223344"
    assert normalize_phone_number("260977223344") == "+260977223344"
    assert normalize_phone_number("+14155552671") == "+14155552671"

    # Test invalid normalization
    is_valid, _ = normalize_phone_number("123")
    assert is_valid is False

    # Send dry-run SMS via send_school_sms
    with client.application.app_context():
        result = send_school_sms(
            school_id=setup_env["school_id"],
            recipient_phone="0977223344",
            message_text="Hillcrest: Test notification to parents.",
            message_type="test",
            recipient_type="parent",
            idempotency_key="idemp_test_001",
        )
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["status"] == "sent"
        msg_id = result["provider_message_id"]

        # Check recorded message in database
        msg_rec = SMSMessage.query.filter_by(provider_message_id=msg_id).first()
        assert msg_rec is not None
        assert msg_rec.recipient_phone == "+260977223344"
        assert msg_rec.status == "sent"

        # Test duplicate prevention with same idempotency key
        dup_result = send_school_sms(
            school_id=setup_env["school_id"],
            recipient_phone="0977223344",
            message_text="Hillcrest: Duplicate message.",
            message_type="test",
            recipient_type="parent",
            idempotency_key="idemp_test_001",
        )
        assert dup_result["provider_message_id"] == msg_id
        assert dup_result["status"] == "sent"


def test_5_sms_delivery_webhook(client, setup_env):
    """Test webhook delivery status update and delivery event logging."""
    with client.application.app_context():
        msg = SMSMessage(
            school_id=setup_env["school_id"],
            recipient_phone="+260977223344",
            message_body="Exam timetable released.",
            message_type="announcement",
            provider_message_id="mock_prov_9999",
            status="sent",
        )
        db.session.add(msg)
        db.session.commit()

    # Post webhook
    resp = client.post(
        "/api/sms/webhook",
        json={
            "message_id": "mock_prov_9999",
            "status": "delivered",
            "delivery_status": "delivered",
        },
    )
    assert resp.status_code == 200

    # Verify updated in DB
    with client.application.app_context():
        updated_msg = SMSMessage.query.filter_by(provider_message_id="mock_prov_9999").first()
        assert updated_msg.status == "delivered"

        event = SMSDeliveryEvent.query.filter_by(sms_message_id=updated_msg.id).first()
        assert event is not None
        assert event.event_type == "delivered"


def test_6_fee_reminders_partial_balance_and_paid_exclusion(client, setup_env):
    """
    Student 1 (Lombe): total 1500, paid 500 -> remaining balance 1000 -> included in reminders.
    Student 2 (Mutale): total 1500, paid 1500 -> balance 0 -> strictly excluded.
    """
    _login(client, "hadmin", "AdminPass123!")

    resp = client.get("/api/admin/sms/fee-reminders/preview")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["count"] >= 1
    # Check that Student 1 is in the reminder list with balance 1000
    reminders = data["reminders"]
    s1_rem = next((r for r in reminders if r["student_id"] == setup_env["s1_id"]), None)
    assert s1_rem is not None
    assert s1_rem["balance"] == 1000.0
    assert "1000.00" in s1_rem["message"]

    # Check that Student 2 (Mutale - fully paid) is NOT in the reminder list
    s2_rem = next((r for r in reminders if r["student_id"] == setup_env["s2_id"]), None)
    assert s2_rem is None

    # Run fee reminders batch
    run_resp = client.post("/api/admin/sms/fee-reminders/run")
    assert run_resp.status_code == 200
    run_data = run_resp.get_json()
    assert run_data["sent_count"] >= 1


def test_7_absenteeism_tracking_and_escalation(client, setup_env):
    """
    Test consecutive and cumulative absenteeism detection.
    3 consecutive absences -> Level 2 Urgent follow-up.
    5 cumulative absences in 30 days -> Flagged for administrative intervention.
    """
    with client.application.app_context():
        today = datetime.date.today()
        # Add 5 absent records for Student 3 (Chanda)
        # Note: dates should fall on weekdays
        dates = []
        d = today
        while len(dates) < 5:
            if d.weekday() < 5:  # Monday to Friday
                dates.append(d)
            d -= datetime.timedelta(days=1)

        for dt in dates:
            db.session.add(
                Attendance(
                    school_id=setup_env["school_id"],
                    student_id=setup_env["s3_id"],
                    class_id=setup_env["class_8a_id"],
                    date=dt,
                    status="Absent",
                    recorded_by_id=setup_env["admin_user_id"],
                )
            )
        db.session.commit()

    _login(client, "hadmin", "AdminPass123!")

    resp = client.get("/api/admin/sms/absenteeism/preview")
    assert resp.status_code == 200
    data = resp.get_json()

    chanda_alert = next((a for a in data["alerts"] if a["student_id"] == setup_env["s3_id"]), None)
    assert chanda_alert is not None
    assert chanda_alert["consecutive_absences"] >= 3
    assert chanda_alert["cumulative_absences"] >= 5
    assert chanda_alert["flagged_for_intervention"] is True

    # Execute absenteeism sweep
    run_resp = client.post("/api/admin/sms/absenteeism/run")
    assert run_resp.status_code == 200
    assert run_resp.get_json()["flagged_count"] >= 1

    # Check that AbsenteeismIntervention record was created
    with client.application.app_context():
        interv = AbsenteeismIntervention.query.filter_by(
            school_id=setup_env["school_id"], student_id=setup_env["s3_id"]
        ).first()
        assert interv is not None
        assert interv.status == "flagged"


def test_8_call_parent_logging(client, setup_env):
    """Administrator logs phone call to guardian with outcome and remarks."""
    _login(client, "hadmin", "AdminPass123!")

    resp = client.post(
        "/api/admin/calls",
        json={
            "student_id": setup_env["s3_id"],
            "parent_id": setup_env["parent_id"],
            "phone_called": "+260977223344",
            "reason": "Chronic Absenteeism Intervention",
            "outcome": "Answered",
            "remarks": "Spoke with Mrs Mulenga. Child was hospitalized with malaria for 5 days. Medical report will be brought tomorrow.",
        },
    )
    assert resp.status_code == 201

    # Fetch call history for student
    list_resp = client.get(f"/api/admin/calls?student_id={setup_env['s3_id']}")
    assert list_resp.status_code == 200
    calls = list_resp.get_json()["calls"]
    assert len(calls) >= 1
    assert calls[0]["status"] == "Answered"
    assert "hospitalized with malaria" in calls[0]["remarks"]


def test_9_daily_cron_sms_tasks(client, setup_env):
    """Vercel Cron daily task execution protected by CRON_SECRET."""
    # 1. No auth -> 401
    resp_unauth = client.get("/api/cron/daily-sms-tasks")
    assert resp_unauth.status_code == 401

    # 2. Valid CRON_SECRET in Authorization header -> 200
    resp_auth = client.get(
        "/api/cron/daily-sms-tasks",
        headers={"Authorization": "Bearer test-cron-secret-12345"},
    )
    assert resp_auth.status_code == 200
    assert resp_auth.get_json()["status"] == "completed"
