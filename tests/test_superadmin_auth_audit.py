"""
tests/test_superadmin_auth_audit.py
Comprehensive Superadmin Authentication, Bootstrap, and Recovery Test Suite.
Covers all 13 audit scenarios:
1. Initial Superadmin creation.
2. Prevention of duplicate Superadmin creation.
3. Correct password hashing.
4. Successful Superadmin login (by username and by email).
5. Incorrect password rejection.
6. Email case-insensitive login.
7. Existing Superadmin account preservation.
8. Secure password recovery.
9. Prevention of unauthorized password recovery.
10. Superadmin dashboard access.
11. Normal administrator access restrictions.
12. Database persistence and configuration.
13. Session persistence and logout.
"""
import os
import json
import pytest
from werkzeug.security import check_password_hash
from app import create_app, _create_superadmin
from extensions import db
from models import User, School
from utils import find_user_for_login, handle_superadmin_recovery


@pytest.fixture
def audit_test_app(tmp_path):
    test_db = tmp_path / "test_sa_audit.db"
    test_config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{test_db}",
        "SECRET_KEY": "audit-test-secret-key",
        "SUPERADMIN_EMAIL": "superadmin@schoolstacks.zm",
        "SUPERADMIN_RECOVERY_TOKEN": "test-recovery-token-xyz-123",
        "WTF_CSRF_ENABLED": False,
        "SERVER_NAME": "schoolstacks.local",
    }
    app = create_app(test_config)
    with app.app_context():
        db.create_all()
        # Seed a test school with an ordinary admin
        school = School(name="Test Academy", subdomain="testacademy", email="contact@testacademy.zm", is_active=True)
        db.session.add(school)
        db.session.commit()

        admin = User(
            school_id=school.id,
            username="schooladmin",
            email="admin@testacademy.zm",
            role="admin",
            is_verified=True,
        )
        admin.set_password("AdminPass123!")
        db.session.add(admin)
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(audit_test_app):
    return audit_test_app.test_client()


# ── Test 1: Initial Superadmin creation ─────────────────────────────────
def test_1_initial_superadmin_creation(audit_test_app):
    with audit_test_app.app_context():
        # Clean superadmins first
        User.query.filter_by(role="superadmin").delete()
        db.session.commit()
        assert User.query.filter_by(role="superadmin").first() is None

        _create_superadmin(audit_test_app)
        sa = User.query.filter_by(role="superadmin").first()
        assert sa is not None
        assert sa.username == "superadmin"
        assert sa.email == "superadmin@schoolstacks.zm"
        assert sa.school_id is None
        assert sa.is_superadmin is True
        assert sa.must_change_password is True


# ── Test 2: Prevention of duplicate Superadmin creation ───────────────────
def test_2_prevention_of_duplicate_superadmin(audit_test_app):
    with audit_test_app.app_context():
        # Call bootstrap twice
        _create_superadmin(audit_test_app)
        _create_superadmin(audit_test_app)
        _create_superadmin(audit_test_app)

        count = User.query.filter_by(role="superadmin").count()
        assert count == 1


# ── Test 3: Correct password hashing ─────────────────────────────────────
def test_3_correct_password_hashing(audit_test_app):
    with audit_test_app.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        assert sa is not None
        # Password hash must not be plain text
        assert sa.password_hash != "SuperAdmin123!"
        assert check_password_hash(sa.password_hash, "SuperAdmin123!") is True
        assert check_password_hash(sa.password_hash, "WrongPassword") is False


# ── Test 4: Successful Superadmin login (Username and Email) ─────────────
def test_4_successful_superadmin_login(client, audit_test_app):
    with audit_test_app.app_context():
        _create_superadmin(audit_test_app)

    # 4a. Login via username
    resp1 = client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "SuperAdmin123!"},
    )
    assert resp1.status_code == 200
    data1 = resp1.get_json()
    assert data1["user"]["role"] == "superadmin"
    assert data1["user"]["username"] == "superadmin"

    # Logout
    client.post("/api/auth/logout")

    # 4b. Login via email
    resp2 = client.post(
        "/api/auth/login",
        json={"username": "superadmin@schoolstacks.zm", "password": "SuperAdmin123!"},
    )
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2["user"]["role"] == "superadmin"


# ── Test 5: Incorrect password rejection ─────────────────────────────────
def test_5_incorrect_password_rejection(client):
    # Wrong password with username
    resp1 = client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "DefinitelyWrongPassword999!"},
    )
    assert resp1.status_code == 401
    assert "Invalid username" in resp1.get_json()["error"]

    # Wrong password with email
    resp2 = client.post(
        "/api/auth/login",
        json={"username": "superadmin@schoolstacks.zm", "password": "WrongPassword999!"},
    )
    assert resp2.status_code == 401
    assert "Invalid username" in resp2.get_json()["error"]


# ── Test 6: Email case-insensitive and whitespace-tolerant login ─────────
def test_6_email_case_insensitive_login(client):
    # Mixed case email with leading/trailing spaces
    resp = client.post(
        "/api/auth/login",
        json={"username": "  SuperAdmin@SchoolStacks.ZM  ", "password": "SuperAdmin123!"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["user"]["role"] == "superadmin"

    # Mixed case username 'SuperAdmin'
    client.post("/api/auth/logout")
    resp_user = client.post(
        "/api/auth/login",
        json={"username": "  SuperAdmin  ", "password": "SuperAdmin123!"},
    )
    assert resp_user.status_code == 200
    assert resp_user.get_json()["user"]["role"] == "superadmin"


# ── Test 7: Existing Superadmin account preservation ─────────────────────
def test_7_existing_superadmin_account_preservation(audit_test_app):
    with audit_test_app.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa.set_password("CustomEstablishedPassword2026!")
        db.session.commit()
        old_hash = sa.password_hash

        # Run bootstrap again
        _create_superadmin(audit_test_app)

        # Hash must NOT be reset or modified by normal startup
        sa_after = User.query.filter_by(role="superadmin").first()
        assert sa_after.password_hash == old_hash
        assert check_password_hash(sa_after.password_hash, "CustomEstablishedPassword2026!") is True


# ── Test 8: Secure password recovery ─────────────────────────────────────
def test_8_secure_password_recovery(client, audit_test_app):
    # 8a. Recovery using X-Recovery-Token header
    recover_resp = client.post(
        "/api/auth/superadmin/recover",
        headers={"X-Recovery-Token": "test-recovery-token-xyz-123"},
        json={
            "new_password": "NewRecoveredSecretPass2026!",
            "email": "recovered.superadmin@schoolstacks.zm",
        },
    )
    assert recover_resp.status_code == 200
    rec_data = recover_resp.get_json()
    assert rec_data["must_change_password"] is True
    assert rec_data["email"] == "recovered.superadmin@schoolstacks.zm"

    # 8b. Verify login works with recovered credentials
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "recovered.superadmin@schoolstacks.zm", "password": "NewRecoveredSecretPass2026!"},
    )
    assert login_resp.status_code == 200
    assert login_resp.get_json()["user"]["must_change_password"] is True


# ── Test 9: Prevention of unauthorized password recovery ─────────────────
def test_9_prevention_of_unauthorized_recovery(client):
    # Wrong recovery token
    bad_resp = client.post(
        "/api/auth/superadmin/recover",
        headers={"X-Recovery-Token": "invalid-token"},
        json={"new_password": "HackerPassword!"},
    )
    assert bad_resp.status_code == 401
    assert "Invalid recovery token" in bad_resp.get_json()["error"]

    # Missing recovery token
    missing_resp = client.post(
        "/api/auth/superadmin/recover",
        json={"new_password": "HackerPassword!"},
    )
    assert missing_resp.status_code == 401


# ── Test 10: Superadmin dashboard access ─────────────────────────────────
def test_10_superadmin_dashboard_access(client):
    # Login as Superadmin
    client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "SuperAdmin123!"},
    )

    # Access API overview
    api_resp = client.get("/api/superadmin/overview")
    assert api_resp.status_code == 200
    assert "metrics" in api_resp.get_json()

    # Access HTML dashboard
    html_resp = client.get("/superadmin/")
    assert html_resp.status_code == 200


# ── Test 11: Normal administrator access restrictions ────────────────────
def test_11_normal_admin_cannot_access_superadmin(client):
    # Logout any current session
    client.post("/api/auth/logout")

    # Login as school admin
    login_resp = client.post(
        "/api/auth/login",
        json={
            "username": "schooladmin",
            "password": "AdminPass123!",
            "school_subdomain": "testacademy",
        },
    )
    assert login_resp.status_code == 200
    assert login_resp.get_json()["user"]["role"] == "admin"

    # Attempt to access superadmin API -> must be 403 Forbidden
    api_resp = client.get("/api/superadmin/overview")
    assert api_resp.status_code == 403

    # Attempt to access superadmin HTML -> must be 403 Forbidden
    html_resp = client.get("/superadmin/")
    assert html_resp.status_code == 403


# ── Test 12: Database persistence and configuration ──────────────────────
def test_12_database_persistence_and_configuration(audit_test_app):
    from config import _get_database_url
    url = _get_database_url()
    assert url is not None
    assert len(url) > 0


# ── Test 13: Session persistence and logout ──────────────────────────────
def test_13_session_persistence_and_logout(client):
    # Login
    client.post(
        "/api/auth/login",
        json={"username": "superadmin", "password": "SuperAdmin123!"},
    )

    # Check bootstrap reports authenticated
    boot_resp = client.get("/api/bootstrap")
    assert boot_resp.status_code == 200
    assert boot_resp.get_json()["authenticated"] is True

    # Logout
    logout_resp = client.post("/api/auth/logout")
    assert logout_resp.status_code == 200

    # Check bootstrap reports unauthenticated
    boot_after = client.get("/api/bootstrap")
    assert boot_after.status_code == 200
    assert boot_after.get_json()["authenticated"] is False
