"""Flask application factory."""

import os
import re
import threading

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for, flash, jsonify
from flask_login import login_required, current_user
from . import db
from .auth import auth_bp, login_manager
from .extensions import csrf, limiter
from .tasks import process_url

# Regex for validating youtube_id parameters (11 alphanumeric + hyphen/underscore)
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__, template_folder="templates")

    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY environment variable is required")
    app.secret_key = secret_key

    # Security cookie settings
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Set SESSION_COOKIE_SECURE = True when behind HTTPS in production
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    # Database setup
    pool = db.get_pool(database_url)
    db.init_db(pool)
    app.config["DB_POOL"] = pool

    # Seed admin user
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if admin_pass:
        db.seed_admin(pool, admin_user, admin_pass)

    # CSRF protection
    csrf.init_app(app)

    # Rate limiting
    limiter.init_app(app)

    # Auth
    login_manager.init_app(app)
    app.register_blueprint(auth_bp)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        return response

    @app.teardown_appcontext
    def close_db(exc):
        pass  # pool persists across requests

    # --- Routes ---

    @app.route("/")
    @login_required
    def dashboard():
        tracks = db.get_tracks_for_user(pool, current_user.id)
        return render_template("dashboard.html", tracks=tracks)

    @app.route("/process", methods=["POST"])
    @login_required
    def process():
        from .tasks import clean_youtube_url
        from ytresearch.youtube import extract_video_id

        url = request.form.get("url", "").strip()
        if not url:
            return jsonify({"error": "Please enter a YouTube URL."}), 400

        url = clean_youtube_url(url)
        try:
            video_id = extract_video_id(url)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        if db.track_exists_for_user(pool, current_user.id, video_id):
            return jsonify({"error": "This video has already been processed."}), 409

        # Insert pending row and kick off processing in a background thread
        db.insert_pending_track(pool, current_user.id, url, video_id)
        user_id = current_user.id

        def _run():
            try:
                process_url(url, user_id, pool)
            except Exception:
                pass  # status already set to 'failed' by process_url

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"youtube_id": video_id, "status": "pending"})

    @app.route("/status/<youtube_id>")
    @login_required
    def track_status(youtube_id: str):
        if not _YOUTUBE_ID_RE.match(youtube_id):
            return jsonify({"error": "Invalid video ID"}), 400
        track = db.get_track(pool, current_user.id, youtube_id)
        if track is None:
            return jsonify({"status": "unknown"}), 404
        return jsonify({
            "status": track["status"],
            "title": track.get("title"),
            "error": track.get("error"),
        })

    @app.route("/track/<youtube_id>")
    @login_required
    def track_detail(youtube_id: str):
        if not _YOUTUBE_ID_RE.match(youtube_id):
            flash("Invalid video ID.", "error")
            return redirect(url_for("dashboard"))
        track = db.get_track(pool, current_user.id, youtube_id)
        if track is None:
            flash("Track not found.", "error")
            return redirect(url_for("dashboard"))
        return render_template("track.html", track=track)

    return app
