"""
extensions.py — All Flask extensions including JWT for mobile API
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from flask_cors import CORS

db            = SQLAlchemy()
login_manager = LoginManager()
csrf          = CSRFProtect()
limiter       = Limiter(key_func=get_remote_address)
mail          = Mail()
jwt           = JWTManager()
cors          = CORS()
