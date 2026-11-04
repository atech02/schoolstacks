"""
tenant.py — Multi-tenant middleware
Identifies which school is making the request based on:
1. Authenticated user's school_id (authoritative for logged-in school users)
2. Subdomain (e.g. stmarys.yoursaas.com)
3. Shared-domain session selection (/s/<subdomain> or login school selector for .web.app / localhost)
Attaches it to Flask's g.school and enforces tenant isolation & subscription status.
"""
from flask import g, request, session, redirect, url_for, abort, current_app
from flask_login import current_user
from models import School


RESERVED_SUBDOMAINS = {
    "www", "app", "api", "admin", "superadmin",
    "mail", "smtp", "ftp", "cdn", "static", "assets",
    "docs", "help", "support", "billing",
}


def _extract_subdomain():
    """Return subdomain if request host is a tenant subdomain, else None."""
    host = request.host.split(":")[0].lower()
    base = current_app.config.get("BASE_DOMAIN", "localhost").lower()

    if (
        host in (base, "localhost", "127.0.0.1")
        or host.endswith(".web.app")
        or host.endswith(".firebaseapp.com")
        or host.endswith(".run.app")
        or host.endswith(".vercel.app")
    ):
        return None

    if host.endswith(f".{base}"):
        subdomain = host[: -(len(base) + 1)]
        if subdomain and subdomain not in RESERVED_SUBDOMAINS:
            return subdomain
    return None


def get_current_school():
    """
    Resolve the active School for the current request.
    Security rule: For authenticated non-superadmin users, their own user.school_id
    is authoritative and cannot be overridden by client parameters or session state.
    """
    subdomain = _extract_subdomain()
    subdomain_school = None
    if subdomain:
        subdomain_school = School.query.filter_by(subdomain=subdomain, is_active=True).first()

    if current_user.is_authenticated:
        if current_user.is_superadmin:
            if subdomain_school:
                return subdomain_school
            sel_sub = session.get("selected_school_subdomain")
            if sel_sub:
                return School.query.filter_by(subdomain=sel_sub, is_active=True).first()
            return None

        user_school = School.query.filter_by(id=current_user.school_id, is_active=True).first()
        # Cross-tenant subdomain check: prevent user of School A from browsing School B's subdomain
        if subdomain_school and user_school and subdomain_school.id != user_school.id:
            abort(403)
        return user_school

    # Unauthenticated request: check subdomain first, then shared-domain session selection
    if subdomain_school:
        return subdomain_school

    sel_sub = session.get("selected_school_subdomain")
    if sel_sub:
        return School.query.filter_by(subdomain=sel_sub, is_active=True).first()

    return None


def init_tenant(app):
    """Register before_request hook on the app."""

    @app.before_request
    def resolve_tenant():
        subdomain = _extract_subdomain()
        g.school = get_current_school()

        # If a logged-in school user's school has been suspended, terminate their session immediately
        if current_user.is_authenticated and not current_user.is_superadmin and current_user.school_id:
            if g.school is None:
                from flask_login import logout_user
                from flask import flash, jsonify
                logout_user()
                exempt_public = ("/login", "/logout", "/static", "/assets", "/images", "/health", "/manifest.json", "/sw.js", "/offline", "/api/bootstrap", "/api/auth")
                if not any(request.path.startswith(p) for p in exempt_public):
                    if request.path.startswith("/api/"):
                        return jsonify({"error": "This school account is currently suspended by the platform administrator.", "school_suspended": True}), 403
                    flash("This school account is currently suspended.", "danger")
                    return redirect(url_for("auth.login"))

        # If we're on a school subdomain but can't find an active school → 404
        if subdomain and g.school is None:
            abort(404)

        # If school exists but subscription expired → redirect to billing (or 402 JSON for /api)
        if g.school and not g.school.subscription_active():
            exempt_prefixes = (
                "/billing",
                "/auth",
                "/login",
                "/logout",
                "/static",
                "/assets",
                "/images",
                "/health",
                "/manifest.json",
                "/sw.js",
                "/offline",
                "/api/bootstrap",
                "/api/auth",
                "/api/billing",
                "/api/onboarding",
            )
            if not any(request.path.startswith(p) for p in exempt_prefixes):
                if request.path.startswith("/api/"):
                    from flask import jsonify
                    return jsonify({"error": "School subscription has expired.", "subscription_expired": True}), 402
                return redirect(url_for("billing.expired"))
