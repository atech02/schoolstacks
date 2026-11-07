"""
tests/test_sms_role_upgrade.py
Comprehensive test suite for the Role-Based School Management System Upgrade.

Covers:
1. Admin Attendance Overview, Register, and Correction Audit Logging.
2. Teacher Attendance roll call with 5 statuses (Present, Late, Absent, Excused, Sick), remarks, and Parent Notifications.
3. Teacher Result Submission -> Admin Approval Workflow -> Student & Parent Visibility (Drafts hidden, Published visible).
4. Report Card PDF generation, attendance stats, and class ranking.
5. Timetable personal schedules & clash detection (teacher, class, room).
6. Multi-Tenant isolation across schools.
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
    Exam,
    Result,
    Attendance,
    TeacherAssignment,
    Timetable,
    ActivityLog,
    Notification,
    utc_now,
)


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test_sms_upgrade.db"
    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-sms-upgrade-secret",
        "UPLOAD_FOLDER": str(tmp_path / "uploads" / "materials"),
        "ASSIGNMENT_UPLOAD": str(tmp_path / "uploads" / "assignments"),
        "ANNOUNCEMENT_UPLOAD": str(tmp_path / "uploads" / "announcements"),
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


@pytest.fixture
def setup_data(app):
    with app.app_context():
        # School 1
        school1 = School(
            name="Apex Academy",
            subdomain="apex",
            email="admin@apex.zm",
            currency="ZMW",
            is_active=True,
        )
        # School 2
        school2 = School(
            name="Beacon Academy",
            subdomain="beacon",
            email="admin@beacon.zm",
            currency="ZMW",
            is_active=True,
        )
        db.session.add_all([school1, school2])
        db.session.flush()

        # Admin 1
        u_admin1 = User(school_id=school1.id, username="apexadmin", email="admin@apex.zm", role="admin", is_verified=True)
        u_admin1.set_password("AdminPass123!")
        # Admin 2
        u_admin2 = User(school_id=school2.id, username="beaconadmin", email="admin@beacon.zm", role="admin", is_verified=True)
        u_admin2.set_password("AdminPass123!")
        db.session.add_all([u_admin1, u_admin2])

        # Classes
        c_10a = SchoolClass(school_id=school1.id, name="Grade 10A", capacity=30, is_active=True)
        c_10b = SchoolClass(school_id=school1.id, name="Grade 10B", capacity=30, is_active=True)
        db.session.add_all([c_10a, c_10b])

        # Term
        t1 = Term(school_id=school1.id, name="Term 1 2026", start_date=datetime.date(2026, 1, 10), end_date=datetime.date(2026, 4, 15))
        db.session.add(t1)

        # Subjects
        math = Subject(school_id=school1.id, name="Mathematics", code="MATH101")
        sci = Subject(school_id=school1.id, name="Integrated Science", code="SCI101")
        db.session.add_all([math, sci])
        db.session.flush()

        # Teacher 1
        u_teach = User(school_id=school1.id, username="T101", email="teacher@apex.zm", role="teacher", is_verified=True)
        u_teach.set_password("Teacher123!")
        db.session.add(u_teach)
        db.session.flush()
        teach = Teacher(school_id=school1.id, user_id=u_teach.id, staff_no="T101", first_name="Grace", last_name="Tembo", phone="0977112233", is_active=True)
        db.session.add(teach)
        db.session.flush()

        # Teacher 2 (for clash testing)
        u_teach2 = User(school_id=school1.id, username="T102", email="teacher2@apex.zm", role="teacher", is_verified=True)
        u_teach2.set_password("Teacher123!")
        db.session.add(u_teach2)
        db.session.flush()
        teach2 = Teacher(school_id=school1.id, user_id=u_teach2.id, staff_no="T102", first_name="Peter", last_name="Banda", phone="0977445566", is_active=True)
        db.session.add(teach2)
        db.session.flush()

        # Teacher assignments
        ta1 = TeacherAssignment(school_id=school1.id, teacher_id=teach.id, class_id=c_10a.id, subject_id=math.id)
        ta2 = TeacherAssignment(school_id=school1.id, teacher_id=teach.id, class_id=c_10a.id, subject_id=sci.id)
        db.session.add_all([ta1, ta2])

        # Students in Grade 10A
        s1 = Student(school_id=school1.id, admission_no="APEX001", first_name="Mwamba", last_name="Mulenga", gender="Male", class_id=c_10a.id, status="active")
        s2 = Student(school_id=school1.id, admission_no="APEX002", first_name="Kondwani", last_name="Phiri", gender="Female", class_id=c_10a.id, status="active")
        db.session.add_all([s1, s2])
        db.session.flush()

        u_s1 = User(school_id=school1.id, username="APEX001", role="student", student_id=s1.id, is_verified=True)
        u_s1.set_password("Student123!")
        u_s2 = User(school_id=school1.id, username="APEX002", role="student", student_id=s2.id, is_verified=True)
        u_s2.set_password("Student123!")
        db.session.add_all([u_s1, u_s2])

        # Parent linked to s1
        u_par = User(school_id=school1.id, username="par_mwamba", email="parent@apex.zm", role="parent", is_verified=True)
        u_par.set_password("Parent123!")
        db.session.add(u_par)
        db.session.flush()
        par = Parent(school_id=school1.id, user_id=u_par.id, first_name="John", last_name="Mulenga", phone="0977998877")
        db.session.add(par)
        db.session.flush()
        ps_link = ParentStudent(school_id=school1.id, parent_id=par.id, student_id=s1.id)
        db.session.add(ps_link)

        # Exam
        exam = Exam(
            school_id=school1.id,
            name="Midterm Exam 2026",
            term_id=t1.id,
            class_id=c_10a.id,
            subject_id=math.id,
            date=datetime.date(2026, 3, 1),
            start_date=datetime.date(2026, 3, 1),
            end_date=datetime.date(2026, 3, 1),
            status="scheduled",
        )
        db.session.add(exam)
        db.session.commit()

        return {
            "school1_id": school1.id,
            "school2_id": school2.id,
            "admin1_id": u_admin1.id,
            "admin2_id": u_admin2.id,
            "teacher_user_id": u_teach.id,
            "teacher_id": teach.id,
            "teacher2_id": teach2.id,
            "student1_id": s1.id,
            "student2_id": s2.id,
            "class10a_id": c_10a.id,
            "class10b_id": c_10b.id,
            "term_id": t1.id,
            "math_id": math.id,
            "sci_id": sci.id,
            "exam_id": exam.id,
            "parent_user_id": u_par.id,
        }


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.get_data(as_text=True)}"
    return resp


# ── Test 1: Teacher Attendance 5-Statuses & Parent Notification ──────────────────
def test_teacher_attendance_roll_call(client, setup_data):
    # Login as Teacher
    _login(client, "T101", "Teacher123!")

    # Mark attendance for class 10A: s1 is Absent with remark, s2 is Present
    today_str = datetime.date.today().isoformat()
    resp = client.post(
        f"/api/teacher/attendance/{setup_data['class10a_id']}",
        json={
            "date": today_str,
            "records": {
                str(setup_data["student1_id"]): "Absent",
                str(setup_data["student2_id"]): "Present",
            },
            "remarks": {
                str(setup_data["student1_id"]): "Called in unwell by family",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["saved"] == 2
    assert data["present_count"] == 1
    assert data["absent_count"] == 1

    # Verify database record
    att1 = Attendance.query.filter_by(student_id=setup_data["student1_id"], date=datetime.date.today()).first()
    assert att1 is not None
    assert att1.status == "Absent"
    assert att1.remarks == "Called in unwell by family"

    att2 = Attendance.query.filter_by(student_id=setup_data["student2_id"], date=datetime.date.today()).first()
    assert att2 is not None
    assert att2.status == "Present"

    # Verify notification created for parent of student 1
    notif = Notification.query.filter_by(user_id=setup_data["parent_user_id"]).first()
    assert notif is not None
    assert "Mwamba" in notif.message or "attendance" in notif.type.lower()


# ── Test 2: Admin Attendance Overview & Correction Audit ────────────────────────
def test_admin_attendance_overview_and_correction(client, setup_data):
    today = datetime.date.today()
    # Pre-seed attendance
    a1 = Attendance(
        school_id=setup_data["school1_id"],
        student_id=setup_data["student1_id"],
        class_id=setup_data["class10a_id"],
        date=today,
        status="Absent",
    )
    db.session.add(a1)
    db.session.commit()

    # Login as Admin
    _login(client, "apexadmin", "AdminPass123!")

    # Check overview
    resp = client.get(f"/api/admin/attendance/overview?date={today.isoformat()}&class_id={setup_data['class10a_id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["summary"]["total_marked"] == 1
    assert data["summary"]["absent_count"] == 1
    assert len(data["absent_today"]) == 1
    assert data["absent_today"][0]["name"] == "Mwamba Mulenga"

    # Perform administrative correction (Absent -> Excused)
    resp_correct = client.post(
        "/api/admin/attendance/correct",
        json={
            "student_id": setup_data["student1_id"],
            "date": today.isoformat(),
            "status": "Excused",
            "reason": "Parent submitted medical certificate",
        },
    )
    assert resp_correct.status_code == 200

    # Verify database updated
    db.session.refresh(a1)
    assert a1.status == "Excused"
    assert "Parent submitted medical certificate" in a1.remarks

    # Verify ActivityLog audit entry
    audit = ActivityLog.query.filter_by(event_type="attendance_corrected", school_id=setup_data["school1_id"]).first()
    assert audit is not None
    assert "Excused" in audit.description


# ── Test 3: Results Workflow: Draft -> Submit -> Admin Approval -> Visibility ────
def test_results_approval_workflow(client, setup_data):
    # 1. Teacher logs in and saves draft
    _login(client, "T101", "Teacher123!")
    c_id = setup_data["class10a_id"]
    s_id = setup_data["math_id"]
    e_id = setup_data["exam_id"]

    draft_resp = client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={
            "action": "save_draft",
            "marks": {
                str(setup_data["student1_id"]): 85.0,
                str(setup_data["student2_id"]): 72.5,
            },
            "remarks": {
                str(setup_data["student1_id"]): "Excellent understanding of algebra",
            },
        },
    )
    assert draft_resp.status_code == 200
    assert draft_resp.get_json()["status"] == "draft"

    # Verify result in DB is draft
    res1 = Result.query.filter_by(student_id=setup_data["student1_id"], exam_id=e_id).first()
    assert res1 is not None
    assert res1.status == "draft"

    # 2. Student & Parent should NOT see draft results
    client.post("/api/auth/logout")
    _login(client, "APEX001", "Student123!")
    s_view = client.get("/api/student/overview").get_json()
    assert len(s_view["results"]) == 0  # Hidden while in draft!

    client.post("/api/auth/logout")
    _login(client, "par_mwamba", "Parent123!")
    p_view = client.get("/api/parent/overview").get_json()
    assert len(p_view["children"][0]["results"]) == 0  # Hidden while in draft!

    # 3. Teacher submits for admin approval
    client.post("/api/auth/logout")
    _login(client, "T101", "Teacher123!")
    submit_resp = client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={"action": "submit_for_approval"},
    )
    assert submit_resp.status_code == 200
    assert submit_resp.get_json()["status"] == "submitted"

    # 4. Admin inspects pending batches and approves
    client.post("/api/auth/logout")
    _login(client, "apexadmin", "AdminPass123!")
    pending_resp = client.get("/api/admin/results/pending")
    assert pending_resp.status_code == 200
    pending_batches = pending_resp.get_json()["pending_batches"]
    assert len(pending_batches) >= 1
    assert pending_batches[0]["exam_id"] == e_id

    # Admin approves
    approve_resp = client.post(
        "/api/admin/results/approve",
        json={"exam_id": e_id, "class_id": c_id, "subject_id": s_id, "action": "approve"},
    )
    assert approve_resp.status_code == 200

    # Verify DB status is published
    db.session.refresh(res1)
    assert res1.status == "published"

    # 5. Now student and parent CAN see the published results
    client.post("/api/auth/logout")
    _login(client, "APEX001", "Student123!")
    s_view_pub = client.get("/api/student/overview").get_json()
    assert len(s_view_pub["results"]) == 1
    assert s_view_pub["results"][0]["marks"] == 85.0

    client.post("/api/auth/logout")
    _login(client, "par_mwamba", "Parent123!")
    p_view_pub = client.get("/api/parent/overview").get_json()
    assert len(p_view_pub["children"][0]["results"]) == 1
    assert p_view_pub["children"][0]["results"][0]["marks"] == 85.0


# ── Test 4: Report Card PDF Generation & Security ──────────────────────────────
def test_report_card_generation_and_access(client, setup_data):
    # Ensure published marks and attendance exist
    res = Result(
        school_id=setup_data["school1_id"],
        student_id=setup_data["student1_id"],
        subject_id=setup_data["math_id"],
        exam_id=setup_data["exam_id"],
        marks=88.0,
        status="published",
    )
    att = Attendance(
        school_id=setup_data["school1_id"],
        student_id=setup_data["student1_id"],
        class_id=setup_data["class10a_id"],
        date=datetime.date.today(),
        status="Present",
    )
    db.session.add_all([res, att])
    db.session.commit()

    # Student downloads their own report card
    _login(client, "APEX001", "Student123!")
    resp = client.get(f"/student/report-card/{setup_data['student1_id']}/{setup_data['term_id']}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Official Report Card" in html
    assert "Mwamba Mulenga" in html
    assert "Mathematics" in html
    assert "Attendance Rate:" in html

    # Parent downloads linked child report card
    client.post("/api/auth/logout")
    _login(client, "par_mwamba", "Parent123!")
    p_resp = client.get(f"/student/report-card/{setup_data['student1_id']}/{setup_data['term_id']}")
    assert p_resp.status_code == 200
    assert "Mwamba Mulenga" in p_resp.get_data(as_text=True)

    # Parent tries to access unlinked student 2 report card -> 403 Forbidden
    unlinked_resp = client.get(f"/student/report-card/{setup_data['student2_id']}/{setup_data['term_id']}")
    assert unlinked_resp.status_code == 403


# ── Test 5: Timetable Management & Clash Detection ──────────────────────────────
def test_timetable_and_clash_detection(client, setup_data):
    # Admin logs in
    _login(client, "apexadmin", "AdminPass123!")

    # 1. Create first entry: Monday 08:00 - 09:00 for Teacher Grace in Grade 10A Room 101
    entry1 = client.post(
        "/api/admin/timetable",
        json={
            "day": "Monday",
            "start_time": "08:00",
            "end_time": "09:00",
            "teacher_id": setup_data["teacher_id"],
            "class_id": setup_data["class10a_id"],
            "subject_id": setup_data["math_id"],
            "room": "Room 101",
        },
    )
    assert entry1.status_code == 201

    # 2. Try to schedule same teacher in another class at the same time -> Clash!
    clash_teacher = client.post(
        "/api/admin/timetable",
        json={
            "day": "Monday",
            "start_time": "08:30",
            "end_time": "09:30",
            "teacher_id": setup_data["teacher_id"],
            "class_id": setup_data["class10b_id"],
            "subject_id": setup_data["sci_id"],
            "room": "Room 102",
        },
    )
    assert clash_teacher.status_code == 400
    assert "Teacher schedule clash" in clash_teacher.get_json()["error"]

    # 3. Try to schedule same room at overlapping time with different teacher -> Room Clash!
    clash_room = client.post(
        "/api/admin/timetable",
        json={
            "day": "Monday",
            "start_time": "08:15",
            "end_time": "09:15",
            "teacher_id": setup_data["teacher2_id"],
            "class_id": setup_data["class10b_id"],
            "subject_id": setup_data["sci_id"],
            "room": "Room 101",
        },
    )
    assert clash_room.status_code == 400
    assert "Room clash" in clash_room.get_json()["error"]

    # 4. Teacher personal timetable check
    client.post("/api/auth/logout")
    _login(client, "T101", "Teacher123!")
    tt_resp = client.get("/api/teacher/timetable")
    assert tt_resp.status_code == 200
    tt_data = tt_resp.get_json()
    assert "Monday" in tt_data["by_day"]
    assert len(tt_data["by_day"]["Monday"]) == 1
    assert tt_data["by_day"]["Monday"][0]["room"] == "Room 101"


# ── Test 6: Multi-Tenant Boundary Isolation Across Schools ──────────────────────
def test_multitenant_boundary_isolation(client, setup_data):
    # Admin of School 2 (Beacon Academy) logs in
    _login(client, "beaconadmin", "AdminPass123!")

    # Attempt to view School 1's attendance overview for School 1 class
    resp = client.get(f"/api/admin/attendance/overview?class_id={setup_data['class10a_id']}")
    assert resp.status_code == 200
    # Should be 0 because class 10A belongs to School 1, not School 2
    assert resp.get_json()["summary"]["total_marked"] == 0

    # Attempt to approve results for School 1 exam -> Should not approve any rows
    bad_approve = client.post(
        "/api/admin/results/approve",
        json={
            "exam_id": setup_data["exam_id"],
            "class_id": setup_data["class10a_id"],
            "subject_id": setup_data["math_id"],
            "action": "approve",
        },
    )
    assert bad_approve.status_code == 404 or bad_approve.get_json().get("updated", 0) == 0


# ── Test 7: Result default status is explicitly draft ───────────────────────────
def test_7_result_default_status_is_draft(app, setup_data):
    # Verify that a newly instantiated Result record with status omitted receives 'draft'
    with app.app_context():
        new_res = Result(
            school_id=setup_data["school1_id"],
            student_id=setup_data["student1_id"],
            subject_id=setup_data["sci_id"],
            exam_id=setup_data["exam_id"],
            marks=76.0,
        )
        db.session.add(new_res)
        db.session.commit()

        db.session.refresh(new_res)
        assert new_res.status == "draft"


# ── Test 8: Teacher cannot modify submitted or published batch ──────────────────
def test_8_teacher_cannot_modify_submitted_or_published_batch(client, setup_data):
    _login(client, "T101", "Teacher123!")
    c_id = setup_data["class10a_id"]
    s_id = setup_data["math_id"]
    e_id = setup_data["exam_id"]

    # 1. Save draft and submit for approval
    client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={"action": "save_draft", "marks": {str(setup_data["student1_id"]): 90.0}},
    )
    submit_resp = client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={"action": "submit_for_approval"},
    )
    assert submit_resp.status_code == 200

    # 2. While submitted, teacher attempts to modify -> HTTP 403 Forbidden (locked)
    edit_attempt = client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={"action": "save_draft", "marks": {str(setup_data["student1_id"]): 99.0}},
    )
    assert edit_attempt.status_code == 403
    assert "submitted for administrator review and locked" in edit_attempt.get_json()["error"]

    # 3. Admin approves and publishes
    client.post("/api/auth/logout")
    _login(client, "apexadmin", "AdminPass123!")
    client.post(
        "/api/admin/results/approve",
        json={"exam_id": e_id, "class_id": c_id, "subject_id": s_id, "action": "approve"},
    )

    # 4. Teacher attempts to modify published results -> HTTP 403 Forbidden (locked)
    client.post("/api/auth/logout")
    _login(client, "T101", "Teacher123!")
    pub_edit = client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={"action": "save_draft", "marks": {str(setup_data["student1_id"]): 50.0}},
    )
    assert pub_edit.status_code == 403
    assert "already been approved and published" in pub_edit.get_json()["error"]


# ── Test 9: Admin reject to draft restores teacher editing with feedback ────────
def test_9_admin_reject_to_draft_restores_teacher_editing_with_feedback(client, setup_data):
    c_id = setup_data["class10a_id"]
    s_id = setup_data["math_id"]
    e_id = setup_data["exam_id"]

    # 1. Ensure submitted result exists
    with client.application.app_context():
        res = Result.query.filter_by(school_id=setup_data["school1_id"], exam_id=e_id, subject_id=s_id).first()
        if not res:
            res = Result(
                school_id=setup_data["school1_id"],
                student_id=setup_data["student1_id"],
                subject_id=s_id,
                exam_id=e_id,
                marks=88.0,
                status="submitted",
            )
            db.session.add(res)
        else:
            res.status = "submitted"
        db.session.commit()

    # 2. Admin returns to draft with feedback
    _login(client, "apexadmin", "AdminPass123!")
    reject_resp = client.post(
        "/api/admin/results/approve",
        json={
            "exam_id": e_id,
            "class_id": c_id,
            "subject_id": s_id,
            "action": "reject_to_draft",
            "feedback": "Please re-verify score for student 1",
        },
    )
    assert reject_resp.status_code == 200
    assert reject_resp.get_json()["status"] == "draft"

    # Verify teacher received notification
    teacher_notif = Notification.query.filter_by(user_id=setup_data["teacher_user_id"]).order_by(Notification.id.desc()).first()
    assert teacher_notif is not None
    assert "returned for revision" in teacher_notif.message
    assert "Please re-verify score for student 1" in teacher_notif.message

    # 3. Teacher editing permission is restored!
    client.post("/api/auth/logout")
    _login(client, "T101", "Teacher123!")
    edit_resp = client.post(
        f"/api/teacher/results/{c_id}/{s_id}/{e_id}",
        json={"action": "save_draft", "marks": {str(setup_data["student1_id"]): 92.0}},
    )
    assert edit_resp.status_code == 200
    assert edit_resp.get_json()["status"] == "draft"


# ── Test 10: Teacher cannot modify another teacher's attendance ─────────────────
def test_10_teacher_cannot_modify_another_teacher_attendance(client, setup_data):
    today = datetime.date.today()
    # 1. Teacher 1 marks attendance
    _login(client, "T101", "Teacher123!")
    client.post(
        f"/api/teacher/attendance/{setup_data['class10a_id']}",
        json={
            "date": today.isoformat(),
            "records": {str(setup_data["student1_id"]): "Present"},
        },
    )

    # 2. Assign Teacher 2 to Grade 10A as well
    with client.application.app_context():
        ta = TeacherAssignment(
            school_id=setup_data["school1_id"],
            teacher_id=setup_data["teacher2_id"],
            class_id=setup_data["class10a_id"],
            subject_id=setup_data["sci_id"],
        )
        db.session.add(ta)
        db.session.commit()

    # 3. Teacher 2 logs in and attempts to modify Teacher 1's attendance -> 403 Forbidden
    client.post("/api/auth/logout")
    _login(client, "T102", "Teacher123!")
    cross_edit = client.post(
        f"/api/teacher/attendance/{setup_data['class10a_id']}",
        json={
            "date": today.isoformat(),
            "allow_edit": True,
            "records": {str(setup_data["student1_id"]): "Absent"},
        },
    )
    assert cross_edit.status_code == 403
    assert "recorded by another teacher" in cross_edit.get_json()["error"]


# ── Test 11: Report card never exposes draft or submitted marks ─────────────────
def test_11_report_card_never_exposes_draft_or_submitted_marks(client, setup_data):
    with client.application.app_context():
        # Subject 1 (Math): Published score of 80.0
        r_pub = Result(
            school_id=setup_data["school1_id"],
            student_id=setup_data["student1_id"],
            subject_id=setup_data["math_id"],
            exam_id=setup_data["exam_id"],
            marks=80.0,
            status="published",
        )
        # Subject 2 (Science): Draft score of 95.0 (UNPUBLISHED)
        r_draft = Result(
            school_id=setup_data["school1_id"],
            student_id=setup_data["student1_id"],
            subject_id=setup_data["sci_id"],
            exam_id=setup_data["exam_id"],
            marks=95.0,
            status="draft",
        )
        db.session.add_all([r_pub, r_draft])
        db.session.commit()

    # Student downloads report card
    _login(client, "APEX001", "Student123!")
    resp = client.get(f"/student/report-card/{setup_data['student1_id']}/{setup_data['term_id']}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Published subject Mathematics must be present
    assert "Mathematics" in html
    assert "80.0" in html

    # Unpublished draft subject Integrated Science must NOT be present!
    assert "Integrated Science" not in html
    assert "95.0" not in html

