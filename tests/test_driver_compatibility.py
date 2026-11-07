"""
tests/test_driver_compatibility.py — Test PostgreSQL driver compatibility and URL normalization.
"""
import os
import pytest
from config import _get_database_url


def test_psycopg_driver_import():
    """Verify that psycopg (v3) is installed and importable."""
    import psycopg
    assert psycopg.__version__ is not None


def test_sqlalchemy_psycopg_engine():
    """Verify that SQLAlchemy dialect for postgresql+psycopg resolves to psycopg driver."""
    from sqlalchemy import create_engine
    engine = create_engine("postgresql+psycopg://user:pass@localhost:5432/testdb")
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_database_url_normalization(monkeypatch):
    """Verify that config._get_database_url normalizes postgres and postgresql schemes to postgresql+psycopg."""
    test_cases = [
        (
            "postgres://user:pass@ep-test.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-test.neon.tech/neondb?sslmode=require",
        ),
        (
            "postgresql://user:pass@ep-test.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-test.neon.tech/neondb?sslmode=require",
        ),
        (
            "postgresql+psycopg://user:pass@ep-test.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-test.neon.tech/neondb?sslmode=require",
        ),
        (
            "postgresql+psycopg2://user:pass@ep-test.neon.tech/neondb?sslmode=require",
            "postgresql+psycopg://user:pass@ep-test.neon.tech/neondb?sslmode=require",
        ),
    ]

    for raw_url, expected in test_cases:
        monkeypatch.setenv("DATABASE_URL", raw_url)
        assert _get_database_url() == expected
