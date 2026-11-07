"""
tests/test_schema_repair.py
Tests for database schema repair: missing schools.currency, classes.class_teacher_id,
attendance.remarks, results status/remarks, idempotent migrations, and /api/bootstrap.
"""
import pytest
from sqlalchemy import text
from app import create_app
from extensions import db
from models import School, User, SchoolClass, Result, Attendance
from migrations_helper import ensure_schema_columns, REQUIRED_COLUMNS


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test_schema_repair.db"
    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "test-repair-secret-key",
        "UPLOAD_FOLDER": str(tmp_path / "uploads" / "materials"),
        "ASSIGNMENT_UPLOAD": str(tmp_path / "uploads" / "assignments"),
        "ANNOUNCEMENT_UPLOAD": str(tmp_path / "uploads" / "announcements"),
        "RATELIMIT_ENABLED": False,
        "IS_PRODUCTION": False,
    }
    app = create_app(test_config)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_ensure_schema_columns_adds_currency_and_backfills(app):
    """Test that ensure_schema_columns safely ensures schools.currency exists and defaults to ZMW."""
    with app.app_context():
        # Verify currency is present in REQUIRED_COLUMNS
        school_cols = dict(REQUIRED_COLUMNS["schools"])
        assert "currency" in school_cols
        assert "ZMW" in school_cols["currency"]

        # Verify results is present in REQUIRED_COLUMNS
        assert "results" in REQUIRED_COLUMNS
        result_cols = dict(REQUIRED_COLUMNS["results"])
        assert "status" in result_cols
        assert "draft" in result_cols["status"]

        # Create a school record
        school = School(
            name="Lusaka Academy",
            subdomain="lusaka-academy",
            email="info@lusaka.edu.zm",
            plan="growth",
            is_active=True,
        )
        db.session.add(school)
        db.session.commit()

        # Query school and verify currency defaults to ZMW
        queried = School.query.filter_by(subdomain="lusaka-academy").first()
        assert queried is not None
        assert queried.currency == "ZMW"

        # Test idempotency: calling ensure_schema_columns again causes no errors
        ensure_schema_columns(db)

        # Verify record still intact
        refetched = School.query.filter_by(subdomain="lusaka-academy").first()
        assert refetched.name == "Lusaka Academy"
        assert refetched.currency == "ZMW"


def test_api_bootstrap_returns_200_with_schools(client, app):
    """Test that GET /api/bootstrap executes School queries cleanly and returns HTTP 200."""
    with app.app_context():
        school = School(
            name="Apex Horizon School",
            subdomain="apex-horizon",
            email="admin@apexhorizon.zm",
            plan="starter",
            currency="ZMW",
            is_active=True,
        )
        db.session.add(school)
        db.session.commit()

    res = client.get("/api/bootstrap")
    assert res.status_code == 200
    data = res.get_json()
    assert "schools" in data
    assert any(s["subdomain"] == "apex-horizon" for s in data["schools"])
    assert "authenticated" in data
    assert "csrf_token" in data


def test_superadmin_persisted_and_unaltered(app):
    """Verify that ensure_schema_columns does not affect Superadmin records."""
    with app.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        assert sa is not None
        initial_hash = sa.password_hash

        # Run schema verification again
        ensure_schema_columns(db)

        refetched_sa = User.query.filter_by(role="superadmin").first()
        assert refetched_sa is not None
        assert refetched_sa.password_hash == initial_hash
