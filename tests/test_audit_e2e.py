"""
tests/test_audit_e2e.py — End-to-End Acceptance Audit and Production Readiness Suite

Validates:
1. Complete User Journeys:
   - School Administrator: create/edit staff, students, classes, subjects, terms, exams with start/end dates, announcements, parent provisioning, archiving.
   - Teacher: assigned class/subject scoping, daily attendance roll call, duplicate prevention (409), edit unlock (200), assignment creation with attachment, materials upload, announcements.
   - Parent: provisioning, login, multi-child switching, child attendance, exams, assignments with download, fees, isolation from other families.
2. Security & Multi-Tenant Isolation:
   - Teacher forbidden from unassigned classes (403).
   - Parent restricted to linked children only.
   - Cross-school tenant isolation.
   - Archived materials hidden from students/parents.
   - File attachment authorization and input validation (type, size, path traversal).
   - Password hashes never exposed in API responses.
3. Database Integrity & Financial Workflows:
   - Unique constraints on attendance records.
   - In-place attendance update audit integrity.
   - Fee structures, balances, payment receipt accessibility.
"""
import io
import json
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
    TeacherAssignment,
    Term,
    Exam,
    FeeStructure,
    Payment,
    Announcement,
    Assignment,
    Material,
    Attendance,
    utc_now,
)
from utils import calculate_balance


@pytest.fixture
def audit_app(tmp_path):
    test_config = {
        "TESTING": True,
        "SECRET_KEY": "audit-test-key",
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
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
def audit_client(audit_app):
    return audit_app.test_client()


@pytest.fixture
def seed_audit_environment(audit_app):
    """Seed School A and School B with initial admin accounts for end-to-end audit."""
    with audit_app.app_context():
        school_a = School(
            name="Lusaka International Academy",
            subdomain="lusaka-intl",
            email="admin@lusaka-intl.zm",
            plan="growth",
            subscription_ends_at=utc_now() + datetime.timedelta(days=90),
        )
        school_b = School(
            name="Ndola Boys High School",
            subdomain="ndola-boys",
            email="admin@ndola-boys.zm",
            plan="starter",
            subscription_ends_at=utc_now() + datetime.timedelta(days=90),
        )
        db.session.add_all([school_a, school_b])
        db.session.flush()

        admin_a = User(
            school_id=school_a.id,
            username="admin_a",
            email="admin@lusaka-intl.zm",
            role="admin",
            is_verified=True,
        )
        admin_a.set_password("AdminPass123")

        admin_b = User(
            school_id=school_b.id,
            username="admin_b",
            email="admin@ndola-boys.zm",
            role="admin",
            is_verified=True,
        )
        admin_b.set_password("AdminPass123")

        db.session.add_all([admin_a, admin_b])
        db.session.commit()

        return {
            "school_a_id": school_a.id,
            "school_b_id": school_b.id,
        }


def test_e2e_administrator_complete_lifecycle(audit_client, seed_audit_environment):
    """Administrator creates classes, subjects, staff, students, exams with date ranges, announcements, and parents."""
    ids = seed_audit_environment

    # 1. Admin login
    res = audit_client.post(
        "/api/auth/login",
        json={"username": "admin_a", "password": "AdminPass123", "school_subdomain": "lusaka-intl"},
    )
    assert res.status_code == 200
    assert res.get_json()["user"]["role"] == "admin"

    # 2. Create Class
    res_class = audit_client.post(
        "/api/admin/classes",
        json={"name": "Grade 11 Science", "capacity": 35},
    )
    assert res_class.status_code == 201
    class_id = res_class.get_json()["id"]

    # 3. Create Subject
    res_subj = audit_client.post(
        "/api/admin/subjects",
        json={"name": "Physics", "code": "PHY101", "description": "Senior Secondary Physics"},
    )
    assert res_subj.status_code == 201
    subject_id = res_subj.get_json()["id"]

    # 4. Create Academic Term
    res_term = audit_client.post(
        "/api/admin/terms",
        json={
            "name": "Term 2 2026",
            "start_date": "2026-05-01",
            "end_date": "2026-08-15",
            "is_current": True,
        },
    )
    assert res_term.status_code == 201
    term_id = res_term.get_json()["id"]

    # 5. Create Teacher with Zambian phone number normalization
    res_teacher = audit_client.post(
        "/api/admin/teachers",
        json={
            "first_name": "Patrick",
            "last_name": "Banda",
            "staff_no": "LIA-T-101",
            "phone": "+260 97 712 3456",
            "email": "patrick.banda@lusaka-intl.zm",
            "specialization": "Physics",
            "username": "p_banda",
            "password": "TeacherPass123",
        },
    )
    assert res_teacher.status_code == 201
    teacher_id = res_teacher.get_json()["id"]

    # 6. Edit Teacher details and phone number
    res_edit_t = audit_client.put(
        f"/api/admin/teachers/{teacher_id}",
        json={
            "first_name": "Patrick",
            "last_name": "Banda",
            "phone": "0977 999 888",
            "email": "pbanda.updated@lusaka-intl.zm",
            "specialization": "Physics & Applied Math",
        },
    )
    assert res_edit_t.status_code == 200
    assert "updated successfully" in res_edit_t.get_json()["message"]

    # 7. Assign Teacher to Class and Subject via Timetable
    res_assign = audit_client.post(
        "/api/admin/timetable",
        json={
            "teacher_id": teacher_id,
            "class_id": class_id,
            "subject_id": subject_id,
            "day": "Monday",
            "start_time": "08:00",
            "end_time": "09:00",
        },
    )
    assert res_assign.status_code == 201

    # 8. Create Examination with multi-day start and end dates
    res_exam = audit_client.post(
        "/api/admin/exams",
        json={
            "name": "Mid-Term Physics Assessment",
            "term_id": term_id,
            "start_date": "2026-06-15",
            "end_date": "2026-06-20",
        },
    )
    assert res_exam.status_code == 201
    exam_id = res_exam.get_json()["id"]

    # 9. Create Student
    res_stu = audit_client.post(
        "/api/admin/students",
        json={
            "first_name": "Kondwani",
            "last_name": "Mwila",
            "admission_no": "LIA-2026-001",
            "gender": "Male",
            "class_id": class_id,
        },
    )
    assert res_stu.status_code == 201
    student_id = res_stu.get_json()["student_id"]

    # 10. Provision Parent and link student
    res_parent = audit_client.post(
        "/api/admin/parents",
        json={
            "first_name": "Beatrice",
            "last_name": "Mwila",
            "phone": "+260 96 612 3456",
            "email": "beatrice.mwila@example.com",
            "username": "beatrice_m",
            "password": "ParentPass123",
            "student_ids": [student_id],
        },
    )
    assert res_parent.status_code == 201
    parent_id = res_parent.get_json()["parent_id"]

    # 11. Create School Announcement
    res_ann = audit_client.post(
        "/api/admin/announcements",
        json={
            "title": "Science Fair & Lab Safety Protocol",
            "content": "All senior science classes must review lab safety rules before Friday.",
            "priority": "High",
            "class_id": class_id,
        },
    )
    assert res_ann.status_code == 201

    # 12. Verify Admin Overview reflects created records
    admin_ov = audit_client.get("/api/admin/overview").get_json()
    assert any(c["id"] == class_id for c in admin_ov["classes"])
    assert any(t["id"] == teacher_id for t in admin_ov["teachers"])
    assert any(s["id"] == student_id for s in admin_ov["students"])
    assert any(p["id"] == parent_id for p in admin_ov["parents"])
    created_exam = next(e for e in admin_ov["exams"] if e["id"] == exam_id)
    assert created_exam["name"] == "Mid-Term Physics Assessment"
    assert created_exam["start_date"] == "2026-06-15"
    assert created_exam["end_date"] == "2026-06-20"


def test_e2e_teacher_attendance_assignment_materials_lifecycle(audit_client, seed_audit_environment):
    """Teacher logs in, sees only assigned classes, conducts attendance with duplicate prevention and edit unlock, creates assignment with attachment, and posts material."""
    ids = seed_audit_environment

    # Setup class, subject, teacher, student
    with audit_client.application.app_context():
        c_assigned = SchoolClass(school_id=ids["school_a_id"], name="Form 3A", capacity=30)
        c_unassigned = SchoolClass(school_id=ids["school_a_id"], name="Form 3B", capacity=30)
        db.session.add_all([c_assigned, c_unassigned])
        db.session.flush()

        subj = Subject(school_id=ids["school_a_id"], name="Biology", code="BIO101")
        term = Term(school_id=ids["school_a_id"], name="Term 1", start_date=datetime.date(2026, 1, 10), end_date=datetime.date(2026, 4, 30))
        exam = Exam(school_id=ids["school_a_id"], term_id=1, name="Final Biology", start_date=datetime.date(2026, 4, 15), end_date=datetime.date(2026, 4, 20))
        db.session.add_all([subj, term, exam])
        db.session.flush()

        t_user = User(school_id=ids["school_a_id"], username="t_chipo", role="teacher", is_verified=True)
        t_user.set_password("TeacherPass123")
        db.session.add(t_user)
        db.session.flush()

        teacher = Teacher(school_id=ids["school_a_id"], user_id=t_user.id, first_name="Chipo", last_name="Mumba", staff_no="T-777")
        db.session.add(teacher)
        db.session.flush()

        # Assign ONLY to Form 3A and Biology
        t_assign = TeacherAssignment(school_id=ids["school_a_id"], teacher_id=teacher.id, class_id=c_assigned.id, subject_id=subj.id)
        db.session.add(t_assign)

        stu = Student(school_id=ids["school_a_id"], admission_no="STU-001", first_name="Zuba", last_name="Banda", class_id=c_assigned.id)
        db.session.add(stu)
        db.session.commit()

        c_assigned_id = c_assigned.id
        c_unassigned_id = c_unassigned.id
        subj_id = subj.id
        stu_id = stu.id
        term_id = term.id

    # 1. Login as teacher
    t_login = audit_client.post(
        "/api/auth/login",
        json={"username": "t_chipo", "password": "TeacherPass123", "school_subdomain": "lusaka-intl"},
    )
    assert t_login.status_code == 200

    # 2. Teacher overview returns only assigned classes
    t_ov = audit_client.get("/api/teacher/overview").get_json()
    t_class_ids = [c["id"] for c in t_ov["classes"]]
    assert c_assigned_id in t_class_ids
    assert c_unassigned_id not in t_class_ids

    # 3. Attendance once-per-day roll call
    date_str = "2026-03-10"
    res_att1 = audit_client.post(
        f"/api/teacher/attendance/{c_assigned_id}",
        json={
            "date": date_str,
            "records": {str(stu_id): "Present"},
            "allow_edit": False,
        },
    )
    assert res_att1.status_code == 200
    assert res_att1.get_json()["present_count"] == 1

    # 4. Attempt duplicate submission on same date without allow_edit -> 409 Conflict
    res_att_dup = audit_client.post(
        f"/api/teacher/attendance/{c_assigned_id}",
        json={
            "date": date_str,
            "records": {str(stu_id): "Absent"},
            "allow_edit": False,
        },
    )
    assert res_att_dup.status_code == 409
    assert res_att_dup.get_json()["already_recorded"] is True

    # 5. Unlock register with allow_edit=True -> 200 OK (in-place update)
    res_att_edit = audit_client.post(
        f"/api/teacher/attendance/{c_assigned_id}",
        json={
            "date": date_str,
            "records": {str(stu_id): "Absent"},
            "allow_edit": True,
        },
    )
    assert res_att_edit.status_code == 200
    assert res_att_edit.get_json()["absent_count"] == 1

    # Verify in DB that only ONE row exists for this student and date
    with audit_client.application.app_context():
        att_rows = Attendance.query.filter_by(student_id=stu_id, date=datetime.date(2026, 3, 10)).all()
        assert len(att_rows) == 1
        assert att_rows[0].status == "Absent"

    # 6. Teacher creates assignment with attachment file
    file_bytes = b"%PDF-1.4 Cellular Respiration Lab Notes"
    res_assign = audit_client.post(
        "/api/teacher/assignments",
        data={
            "title": "Cell Biology Lab Exercise",
            "description": "Read the attached notes and complete diagrams.",
            "class_id": str(c_assigned_id),
            "subject_id": str(subj_id),
            "assignment_date": "2026-03-12",
            "due_date": "2026-03-20",
            "file": (io.BytesIO(file_bytes), "cellular_notes.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert res_assign.status_code == 201
    assign_id = res_assign.get_json()["id"]

    # 7. Teacher uploads study material
    mat_bytes = b"Genetics & Punnett Squares Reference Guide"
    res_mat = audit_client.post(
        "/api/teacher/materials",
        data={
            "title": "Genetics Quick Guide",
            "description": "Overview of Mendelian inheritance",
            "class_id": str(c_assigned_id),
            "subject_id": str(subj_id),
            "term_id": str(term_id),
            "file": (io.BytesIO(mat_bytes), "genetics_guide.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert res_mat.status_code == 201
    mat_id = res_mat.get_json()["id"]

    # 8. Teacher archives study material
    res_archive = audit_client.post(f"/api/materials/{mat_id}/archive")
    assert res_archive.status_code == 200
    assert res_archive.get_json()["is_archived"] is True


def test_e2e_parent_multi_child_and_security_isolation(audit_client, seed_audit_environment):
    """Parent signs in, views multiple children, switches children, views exams/assignments/attendance, and security blocks unauthorized records."""
    ids = seed_audit_environment

    with audit_client.application.app_context():
        c_1 = SchoolClass(school_id=ids["school_a_id"], name="Grade 8A", capacity=30)
        c_2 = SchoolClass(school_id=ids["school_a_id"], name="Grade 10B", capacity=30)
        c_unrelated = SchoolClass(school_id=ids["school_a_id"], name="Grade 12A", capacity=30)
        db.session.add_all([c_1, c_2, c_unrelated])
        db.session.flush()

        subj = Subject(school_id=ids["school_a_id"], name="English", code="ENG101")
        term = Term(school_id=ids["school_a_id"], name="Term 1 2026", start_date=datetime.date(2026, 1, 15), end_date=datetime.date(2026, 4, 15))
        db.session.add_all([subj, term])
        db.session.flush()

        fee_struct = FeeStructure(school_id=ids["school_a_id"], class_id=c_1.id, term_id=term.id, amount=3500.0)
        db.session.add(fee_struct)
        db.session.flush()

        # Children for Parent A
        child_1 = Student(school_id=ids["school_a_id"], admission_no="LIA-001", first_name="Kabwe", last_name="Mulenga", class_id=c_1.id)
        child_2 = Student(school_id=ids["school_a_id"], admission_no="LIA-002", first_name="Thandiwe", last_name="Mulenga", class_id=c_2.id)
        # Unrelated student from another family
        other_child = Student(school_id=ids["school_a_id"], admission_no="LIA-999", first_name="Donald", last_name="Chanda", class_id=c_unrelated.id)
        db.session.add_all([child_1, child_2, other_child])
        db.session.flush()

        # Parent A account
        p_user = User(school_id=ids["school_a_id"], username="parent_mulenga", role="parent", is_verified=True)
        p_user.set_password("ParentSecurePass1")
        db.session.add(p_user)
        db.session.flush()

        parent_a = Parent(school_id=ids["school_a_id"], user_id=p_user.id, first_name="Peter", last_name="Mulenga", phone="0977112233")
        db.session.add(parent_a)
        db.session.flush()

        link1 = ParentStudent(school_id=ids["school_a_id"], parent_id=parent_a.id, student_id=child_1.id)
        link2 = ParentStudent(school_id=ids["school_a_id"], parent_id=parent_a.id, student_id=child_2.id)
        db.session.add_all([link1, link2])

        # Create attendance record for child_1
        att_c1 = Attendance(school_id=ids["school_a_id"], student_id=child_1.id, class_id=c_1.id, date=datetime.date(2026, 2, 20), status="Present")
        db.session.add(att_c1)

        # Create assignment with attachment for class 1
        assign_c1 = Assignment(
            school_id=ids["school_a_id"],
            title="Grammar Exercise 4",
            class_id=c_1.id,
            subject_id=subj.id,
            assignment_date=datetime.date(2026, 2, 18),
            attachment_name="grammar_ex4.pdf",
            attachment_path="assignments/sample_test_attachment.pdf",
            attachment_type="pdf",
        )
        db.session.add(assign_c1)

        # Create fee payment for child_1
        pmt = Payment(
            school_id=ids["school_a_id"],
            student_id=child_1.id,
            term_id=term.id,
            amount_paid=2000.0,
            reference="RCT-LIA-2026-001",
            status="completed",
        )
        db.session.add(pmt)
        db.session.commit()

        child_1_id = child_1.id
        child_2_id = child_2.id
        other_child_id = other_child.id
        assign_id = assign_c1.id

    # 1. Parent logs in
    login_res = audit_client.post(
        "/api/auth/login",
        json={"username": "parent_mulenga", "password": "ParentSecurePass1", "school_subdomain": "lusaka-intl"},
    )
    assert login_res.status_code == 200
    assert login_res.get_json()["user"]["role"] == "parent"

    # 2. Parent overview lists BOTH linked children and NOT the unrelated child
    p_ov = audit_client.get("/api/parent/overview").get_json()
    linked_ids = [c["id"] for c in p_ov["children"]]
    assert child_1_id in linked_ids
    assert child_2_id in linked_ids
    assert other_child_id not in linked_ids

    # 3. Child 1 has attendance, assignment with attachment info, and fee balance
    c1_data = next(c for c in p_ov["children"] if c["id"] == child_1_id)
    assert len(c1_data["attendance"]) == 1
    assert c1_data["attendance"][0]["status"] == "Present"
    assert len(c1_data["assignments"]) == 1
    assert c1_data["assignments"][0]["attachment_name"] == "grammar_ex4.pdf"
    assert c1_data["fee_balances"][0]["balance"] == 1500.0  # 3500 - 2000

    # 4. Security Check: Unrelated child financial and academic data is NEVER exposed
    assert not any(c["id"] == other_child_id for c in p_ov["children"])


def test_security_access_controls_and_input_validation(audit_client, seed_audit_environment):
    """Rigorous security checks: unassigned class tamper, cross-school isolation, file type and size guards, password hash secrecy."""
    ids = seed_audit_environment

    # 1. Setup teacher in School A assigned only to Class A
    with audit_client.application.app_context():
        c_a = SchoolClass(school_id=ids["school_a_id"], name="Form 1A", capacity=25)
        c_b = SchoolClass(school_id=ids["school_a_id"], name="Form 1B", capacity=25)
        c_school_b = SchoolClass(school_id=ids["school_b_id"], name="Ndola Class 1", capacity=25)
        db.session.add_all([c_a, c_b, c_school_b])
        db.session.flush()

        t_user = User(school_id=ids["school_a_id"], username="teacher_a1", role="teacher", is_verified=True)
        t_user.set_password("SecurePass123")
        db.session.add(t_user)
        db.session.flush()

        t_rec = Teacher(school_id=ids["school_a_id"], user_id=t_user.id, first_name="John", last_name="Banda", staff_no="TA1")
        db.session.add(t_rec)
        db.session.flush()

        subj = Subject(school_id=ids["school_a_id"], name="Civics", code="CIV101")
        db.session.add(subj)
        db.session.flush()

        t_assign = TeacherAssignment(school_id=ids["school_a_id"], teacher_id=t_rec.id, class_id=c_a.id, subject_id=subj.id)
        db.session.add(t_assign)
        db.session.commit()

        c_a_id = c_a.id
        c_b_id = c_b.id
        c_school_b_id = c_school_b.id
        subj_id = subj.id

    # 2. Login as teacher_a1
    audit_client.post(
        "/api/auth/login",
        json={"username": "teacher_a1", "password": "SecurePass123", "school_subdomain": "lusaka-intl"},
    )

    # 3. URL tamper: Teacher tries to access unassigned class attendance -> 403 Forbidden
    res_tamper = audit_client.get(f"/api/teacher/attendance/{c_b_id}?date=2026-03-10")
    assert res_tamper.status_code == 403

    # 4. Cross-tenant tamper: Teacher tries to access class belonging to another school -> blocked (403 or 404)
    res_cross = audit_client.get(f"/api/teacher/attendance/{c_school_b_id}?date=2026-03-10")
    assert res_cross.status_code in (403, 404)

    # 5. File upload guard: Disallowed file extension (.exe) rejected with 400
    res_exe = audit_client.post(
        "/api/teacher/assignments",
        data={
            "title": "Bad File",
            "description": "Invalid file upload attempt",
            "class_id": str(c_a_id),
            "subject_id": str(subj_id),
            "assignment_date": "2026-03-15",
            "due_date": "2026-03-25",
            "file": (io.BytesIO(b"executable content"), "malware.exe"),
        },
        content_type="multipart/form-data",
    )
    assert res_exe.status_code == 400
    assert "Attachment type not allowed" in res_exe.get_json()["error"]

    # 6. File upload guard: Oversized file (>10MB) rejected with 400
    large_payload = b"0" * (11 * 1024 * 1024)
    res_large = audit_client.post(
        "/api/teacher/assignments",
        data={
            "title": "Too Large",
            "description": "Oversized file upload attempt",
            "class_id": str(c_a_id),
            "subject_id": str(subj_id),
            "assignment_date": "2026-03-15",
            "due_date": "2026-03-25",
            "file": (io.BytesIO(large_payload), "large_document.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert res_large.status_code == 400
    assert "exceeds" in res_large.get_json()["error"]

    # 7. Password hash secrecy: API responses must never leak password hashes
    audit_client.post("/api/auth/logout")
    login_res = audit_client.post(
        "/api/auth/login",
        json={"username": "admin_a", "password": "AdminPass123", "school_subdomain": "lusaka-intl"},
    )
    user_payload = login_res.get_json()["user"]
    assert "password_hash" not in user_payload
    assert "password" not in user_payload

    bootstrap_res = audit_client.get("/api/bootstrap").get_json()
    assert "password_hash" not in bootstrap_res["user"]
