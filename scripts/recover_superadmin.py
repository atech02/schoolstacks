#!/usr/bin/env python3
"""
scripts/recover_superadmin.py — Secure Administrative Recovery CLI for SchoolStacks / School-Magi

Usage:
    python scripts/recover_superadmin.py --sync-env
    python scripts/recover_superadmin.py --email admin@example.com --password MyNewPassword123!
    python scripts/recover_superadmin.py --interactive

Requirements:
    - Runs in the application environment (local terminal, container, or server).
    - Uses werkzeug.security.generate_password_hash to ensure consistent password hashing.
    - Idempotently updates or provisions the Super Administrator without touching school data.
    - Normalizes the email address to lowercase.
    - Never logs plain-text passwords.
"""
import os
import sys
import argparse
import getpass

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from extensions import db
from models import User
from werkzeug.security import generate_password_hash, check_password_hash


def recover_superadmin(email: str | None = None, password: str | None = None, sync_env: bool = False):
    app = create_app()

    with app.app_context():
        final_email = email
        final_password = password

        if sync_env:
            final_email = (
                final_email
                or os.environ.get("SUPERADMIN_EMAIL")
                or app.config.get("SUPERADMIN_EMAIL")
            )
            final_password = (
                final_password
                or os.environ.get("SUPERADMIN_PASSWORD")
                or os.environ.get("ADMIN_PASSWORD")
            )

        if not final_email:
            final_email = os.environ.get("SUPERADMIN_EMAIL") or app.config.get("SUPERADMIN_EMAIL") or "superadmin@edumanage.zm"

        final_email = final_email.strip().lower()

        if not final_password:
            print("[PROMPT] Enter new password for Superadmin:", file=sys.stderr)
            final_password = getpass.getpass("Password: ")
            if not final_password:
                print("Error: Password cannot be empty.", file=sys.stderr)
                sys.exit(1)

        # Locate existing superadmin account
        sa = User.query.filter_by(role="superadmin").first()
        if not sa:
            sa = User.query.filter_by(email=final_email).first()

        created = False
        if not sa:
            sa = User(
                school_id=None,
                username="superadmin",
                email=final_email,
                password_hash=generate_password_hash(final_password),
                role="superadmin",
                is_verified=True,
                must_change_password=True,
            )
            db.session.add(sa)
            created = True
        else:
            sa.username = "superadmin"
            sa.email = final_email
            sa.password_hash = generate_password_hash(final_password)
            sa.is_verified = True
            sa.must_change_password = True

        db.session.commit()

        # Verify integrity
        verified = check_password_hash(sa.password_hash, final_password)
        if not verified:
            print("ERROR: Password hash verification failed immediately after commitment.", file=sys.stderr)
            sys.exit(1)

        action_str = "created" if created else "updated"
        print(f"[SUCCESS] Super Administrator account {action_str} successfully.")
        print(f"  Username: {sa.username}")
        print(f"  Email:    {sa.email}")
        print(f"  Role:     {sa.role}")
        print(f"  Verified: {sa.is_verified}")
        print(f"  Must Change Password: {sa.must_change_password}")


def main():
    parser = argparse.ArgumentParser(description="SchoolStacks Superadmin Recovery Tool")
    parser.add_argument("--email", help="Superadmin email address")
    parser.add_argument("--password", help="New superadmin password (prefer interactive or --sync-env)")
    parser.add_argument("--sync-env", action="store_true", help="Synchronize credentials from SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD / ADMIN_PASSWORD")
    parser.add_argument("--interactive", action="store_true", help="Prompt for credentials interactively")

    args = parser.parse_args()

    if args.interactive:
        email = input("Superadmin Email: ").strip()
        pwd = getpass.getpass("Superadmin Password: ")
        recover_superadmin(email=email, password=pwd)
    elif args.sync_env or args.email or args.password:
        recover_superadmin(email=args.email, password=args.password, sync_env=args.sync_env)
    else:
        # Default to sync-env if no options specified
        print("No flags specified; defaulting to environment synchronization (--sync-env)...")
        recover_superadmin(sync_env=True)


if __name__ == "__main__":
    main()
