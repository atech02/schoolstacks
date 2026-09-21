"""
app.py — SaaS app factory with REST API layer for mobile app
"""
import os
from flask import Flask, jsonify
from config import Config
from extensions import db, login_manager, csrf, limiter, mail, jwt, cors
from models import User
from tenant import init_tenant
from werkzeug.security import generate_password_hash


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
             
    # ── JWT config ────────────────────────────────────────────────
    app.config["JWT_SECRET_KEY"]          = app.config["SECRET_KEY"]
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False  # set in production
    app.config["JWT_REFRESH_TOKEN_EXPIRES"]= False

    # ── CORS: allow mobile app to call the API ────────────────────
    app.config["CORS_ORIGINS"] = ["*"]  # restrict in production
         
    # ── Extensions ────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    
    login_manager.login_view             = "auth.login"
    login_manager.login_message_category = "warning"
         
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
                          
    # ── Exempt API routes from CSRF (JWT handles security there) ──
    csrf.exempt("api_auth")
    csrf.exempt("students_api")
    csrf.exempt("school_api")

    # ── JWT error handlers ─────────────────────────────────────────
    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({"error": "Token expired", "code": "TOKEN_EXPIRED"}), 401
                     
    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"error": "Invalid token", "code": "INVALID_TOKEN"}), 401

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"error": "Authorization required", "code": "NO_TOKEN"}), 401
                 
    # ── Multi-tenant middleware ────────────────────────────────────
    init_tenant(app)

    # ── Web Blueprints ────────────────────────────────────────────
    from blueprints.onboarding import onboarding
    from blueprints.billing    import billing
    from blueprints.superadmin import superadmin
    from blueprints.auth       import auth
    from blueprints.admin      import admin
    from blueprints.teacher    import teacher
    from blueprints.student    import student
    from blueprints.parent     import parent

    app.register_blueprint(onboarding)
    app.register_blueprint(billing)
    app.register_blueprint(superadmin)
    app.register_blueprint(auth)
    app.register_blueprint(admin)
    app.register_blueprint(teacher)
    app.register_blueprint(student)
    app.register_blueprint(parent)

    # ── API Blueprints (mobile) ───────────────────────────────────
    from api.blueprints.auth_api    import api_auth
    from api.blueprints.students_api import students_api
    from api.blueprints.school_api  import school_api
                 
    API_PREFIX = "/api/v1"
    app.register_blueprint(api_auth,    url_prefix=f"{API_PREFIX}/auth")
    app.register_blueprint(students_api, url_prefix=API_PREFIX)
    app.register_blueprint(school_api,  url_prefix=API_PREFIX)
    
    # ── API health check ──────────────────────────────────────────
    @app.route("/api/v1/health")
    def api_health():
        return jsonify({"status": "ok", "version": "1.0"}), 200
                     
    # ── Uploads ───────────────────────────────────────────────────
    for folder in [
            app.config["UPLOAD_FOLDER"],
            app.config["ASSIGNMENT_UPLOAD"],
            app.config["ANNOUNCEMENT_UPLOAD"],
            ]:
        os.makedirs(folder, exist_ok=True)

    with app.app_context():
        db.create_all()
        _create_superadmin(app)
        

    _start_scheduler(app)
    return app


def _create_superadmin(app):
    if not User.query.filter_by(role="superadmin").first():
        password = os.environ.get("ADMIN_PASSWORD", "SuperAdmin123!")
        sa = User(
                school_id=None, username="superadmin",
                email=app.config["SUPERADMIN_EMAIL"],
                password_hash=generate_password_hash(password),
                role="superadmin", is_verified=True,
                )
        db.session.add(sa)
        db.session.commit()
        print("✅ Superadmin created")


def _start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: None, "interval", weeks=1)
        scheduler.start()
    except ImportError:
        pass
                                                         
                                                         
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
