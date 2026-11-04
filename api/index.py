"""
api/index.py — Vercel Serverless Function WSGI entrypoint.
Imports the configured Flask application factory from app.py.
Preserves all blueprints, multi-tenant middleware, session handlers, and error handlers.
"""
import os
import sys

# Ensure application root is in python path
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from app import create_app

app = create_app()
