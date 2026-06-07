"""Flask-Login authentication setup."""

from urllib.parse import urlparse

from flask import Blueprint, redirect, render_template, request, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from werkzeug.security import check_password_hash

from . import db
from .extensions import limiter

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()
login_manager.login_view = "auth.login"


class User(UserMixin):
    def __init__(self, user_dict: dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.password_hash = user_dict["password_hash"]


@login_manager.user_loader
def load_user(user_id: str):
    from flask import current_app
    pool = current_app.config["DB_POOL"]
    user_dict = db.get_user_by_id(pool, int(user_id))
    if user_dict is None:
        return None
    return User(user_dict)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10/minute", methods=["POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    from flask import current_app
    pool = current_app.config["DB_POOL"]
    user_dict = db.get_user_by_username(pool, username)

    if user_dict is None or not check_password_hash(user_dict["password_hash"], password):
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401

    login_user(User(user_dict))
    next_page = request.args.get("next", "")
    # Prevent open redirect — only allow relative paths on this host
    if next_page:
        parsed = urlparse(next_page)
        if parsed.netloc or parsed.scheme:
            next_page = ""
    return redirect(next_page or url_for("dashboard"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
