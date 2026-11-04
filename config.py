"""
config.py — Application configuration using environment variables and safe development defaults.
"""
import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _get_database_url():
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if not db_url:
        instance_dir = os.path.join(BASE_DIR, "instance")
        os.makedirs(instance_dir, exist_ok=True)
        db_url = f"sqlite:///{os.path.join(instance_dir, 'edumanage.db')}"
    return db_url


class Config:
    # ── Core Flask & Security ──────────────────────────────────────
    ENV = os.environ.get("FLASK_ENV", "development").lower()
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    TESTING = False
    IS_PRODUCTION = ENV == "production" or bool(os.environ.get("K_SERVICE"))

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-edumanage-secret-key-change-in-prod")
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION

    # ── Database ───────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # ── Multi-tenant & Domain ──────────────────────────────────────
    BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")
    APP_PROTOCOL = os.environ.get("APP_PROTOCOL", "https" if IS_PRODUCTION else "http")
    SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL", "superadmin@edumanage.zm")

    # ── Uploads ────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads", "materials"))
    ASSIGNMENT_UPLOAD = os.environ.get("ASSIGNMENT_UPLOAD", os.path.join(BASE_DIR, "uploads", "assignments"))
    ANNOUNCEMENT_UPLOAD = os.environ.get("ANNOUNCEMENT_UPLOAD", os.path.join(BASE_DIR, "uploads", "announcements"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "png", "jpg", "jpeg"}

    # ── Mail ───────────────────────────────────────────────────────
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@edumanage.zm")

    # ── Rate Limiting ──────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # ── Lipila Payment Gateway Configuration (ZMW) ─────────────────
    LIPILA_ENV = os.environ.get("LIPILA_ENV", "sandbox").lower()
    LIPILA_SANDBOX_URL = os.environ.get("LIPILA_SANDBOX_URL", "https://api.lipila.dev/api/v1")
    LIPILA_LIVE_URL = os.environ.get("LIPILA_LIVE_URL", "https://api.lipila.io/api/v1")
    LIPILA_API_KEY = os.environ.get("LIPILA_API_KEY", "").strip()
    LIPILA_WEBHOOK_SECRET = os.environ.get("LIPILA_WEBHOOK_SECRET", "").strip()
    LIPILA_CALLBACK_URL = os.environ.get("LIPILA_CALLBACK_URL", "").strip()
    LIPILA_CURRENCY = os.environ.get("LIPILA_CURRENCY", "ZMW")

    # Sandbox simulator is ONLY allowed in non-production environments when no live API key is set
    LIPILA_SIMULATOR_ENABLED = (
        not IS_PRODUCTION
        and LIPILA_ENV != "production"
        and not bool(LIPILA_API_KEY)
    )

    # ── SaaS Plans & Pricing Catalogue (ZMW) ───────────────────────
    PLAN_LIMITS = {
        "free":       {"students": 50,    "teachers": 5},
        "starter":    {"students": 250,   "teachers": 25},
        "growth":     {"students": 1000,  "teachers": 100},
        "enterprise": {"students": 10000, "teachers": 1000},
    }

    PLAN_FEATURES = {
        "free": [
            "Up to 50 students & 5 teachers",
            "Attendance & Basic Results",
            "14-day trial of full platform",
        ],
        "starter": [
            "Up to 250 students & 25 teachers",
            "Lipila Mobile Money & Card Fee Collection",
            "PDF Report Cards & Receipts",
            "Parent & Student Portals",
        ],
        "growth": [
            "Up to 1,000 students & 100 teachers",
            "Everything in Starter",
            "School Performance Analytics",
            "Automated Fee Reminders & Announcements",
        ],
        "enterprise": [
            "Unlimited students & teachers (10,000+)",
            "Everything in Growth",
            "Dedicated Priority Support & Custom Branding",
            "Multi-campus & Custom SLA",
        ],
    }

    PLAN_PRICES = {
        "free": {
            "name": "Free Trial",
            "currency": "ZMW",
            "amount_monthly": 0.0,
            "amount_yearly": 0.0,
        },
        "starter": {
            "name": "Starter",
            "currency": "ZMW",
            "amount_monthly": 450.0,
            "amount_yearly": 4500.0,
        },
        "growth": {
            "name": "Growth",
            "currency": "ZMW",
            "amount_monthly": 950.0,
            "amount_yearly": 9500.0,
        },
        "enterprise": {
            "name": "Enterprise",
            "currency": "ZMW",
            "amount_monthly": 2200.0,
            "amount_yearly": 22000.0,
        },
    }

    # Alias kept for backward compatibility with existing templates/helpers
    STRIPE_PRICES = PLAN_PRICES
