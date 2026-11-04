"""
app.py — SaaS application factory
"""
import os
import logging
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_login import current_user
from werkzeug.security import generate_password_hash
from config import Config
from extensions import db, migrate, login_manager, csrf, limiter, mail
from models import User, School
from tenant import init_tenant
from migrations_helper import ensure_schema_columns

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app(config_class=Config):
    app = Flask(__name__)
    if isinstance(config_class, dict):
        app.config.from_object(Config)
        app.config.update(config_class)
    else:
        app.config.from_object(config_class)

    # ── Extensions ────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    # ── Multi-tenant middleware ────────────────────────────────────
    init_tenant(app)

    # ── Security & Cache headers for private/payment responses ────
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        origin = request.headers.get("Origin", "")
        if origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        if (
            current_user.is_authenticated
            or request.path.startswith("/api")
            or request.path.startswith("/billing")
            or request.path.startswith("/admin")
            or request.path.startswith("/teacher")
            or request.path.startswith("/student")
            or request.path.startswith("/parent")
            or request.path.startswith("/superadmin")
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response

    # ── Blueprints ────────────────────────────────────────────────
    from blueprints.onboarding import onboarding
    from blueprints.billing    import billing
    from blueprints.superadmin import superadmin
    from blueprints.auth       import auth
    from blueprints.admin      import admin
    from blueprints.teacher    import teacher
    from blueprints.student    import student
    from blueprints.parent     import parent
    from blueprints.api        import api

    app.register_blueprint(onboarding)
    app.register_blueprint(billing)
    app.register_blueprint(superadmin)
    app.register_blueprint(auth)
    app.register_blueprint(admin)
    app.register_blueprint(teacher)
    app.register_blueprint(student)
    app.register_blueprint(parent)
    app.register_blueprint(api)

    # ── React SPA static assets, root images & client-side route handler ──
    react_dist_dir = os.path.join(app.root_path, "frontend", "dist")
    root_images_dir = os.path.join(app.root_path, "images")

    @app.route("/assets/<path:filename>")
    def react_assets(filename):
        return send_from_directory(os.path.join(react_dist_dir, "assets"), filename)

    @app.route("/images/<path:filename>")
    def project_images(filename):
        return send_from_directory(root_images_dir, filename)

    @app.before_request
    def serve_react_spa():
        if app.config.get("TESTING"):
            return None
        if request.method != "GET":
            return None
        index_html = os.path.join(react_dist_dir, "index.html")
        if not os.path.isfile(index_html):
            return None

        path = request.path
        passthrough_prefixes = (
            "/api/",
            "/static/",
            "/assets/",
            "/images/",
            "/health",
            "/manifest.json",
            "/sw.js",
            "/offline",
            "/s/",
            "/verify/",
            "/admin/download/",
            "/student/report-card/",
            "/billing/webhook/",
        )
        if any(path.startswith(p) for p in passthrough_prefixes):
            return None

        resp = send_from_directory(react_dist_dir, "index.html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return resp

    # ── Health check & PWA root routes ────────────────────────────
    @app.route("/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": "edumanage-saas",
            "lipila_env": app.config.get("LIPILA_ENV", "sandbox"),
            "simulator_enabled": bool(app.config.get("LIPILA_SIMULATOR_ENABLED", False)),
        }), 200

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "manifest.json",
            mimetype="application/manifest+json",
        )

    @app.route("/sw.js")
    def service_worker():
        resp = send_from_directory(
            os.path.join(app.root_path, "static"),
            "sw.js",
            mimetype="application/javascript",
        )
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Service-Worker-Allowed"] = "/"
        return resp

    @app.route("/offline")
    def offline():
        return render_template("offline.html")

    # ── Upload directories ─────────────────────────────────────────
    for folder in [
        app.config["UPLOAD_FOLDER"],
        app.config["ASSIGNMENT_UPLOAD"],
        app.config["ANNOUNCEMENT_UPLOAD"],
    ]:
        os.makedirs(folder, exist_ok=True)

    # ── DB init, non-destructive column migrations + superadmin ───
    with app.app_context():
        db.create_all()
        ensure_schema_columns(db)
        _create_superadmin(app)

    # ── Scheduler (skip during unit tests) ────────────────────────
    if not app.config.get("TESTING"):
        _start_scheduler(app)

    return app


def _create_superadmin(app):
    sa_email = app.config["SUPERADMIN_EMAIL"]
    if not User.query.filter_by(role="superadmin").first():
        password = os.environ.get("ADMIN_PASSWORD", "SuperAdmin123!")
        sa = User(
            school_id=None,
            username="superadmin",
            email=sa_email,
            password_hash=generate_password_hash(password),
            role="superadmin",
            is_verified=True,
        )
        db.session.add(sa)
        db.session.commit()


def _start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        def run_fee_reminders():
            with app.app_context():
                from utils import check_fee_reminders
                check_fee_reminders()

        scheduler = BackgroundScheduler()
        scheduler.add_job(run_fee_reminders, "interval", weeks=1)
        scheduler.start()
    except ImportError:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("PORT", 5000))
    application.run(host="0.0.0.0", port=port, debug=application.config.get("DEBUG", False))
