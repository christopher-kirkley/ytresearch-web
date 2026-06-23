"""SQLite database backend for ytresearch-web.

Shares the archive the `ytresearch` CLI writes to (default
~/music-archive/archive.db). The web app adds a `users` table for login plus a
few workflow columns (`user_id`, `status`, `error`) onto the existing `tracks`
table, so tracks archived by the CLI show up in the web UI.

Single-tenant: login gates access, but the whole archive is shared. Tracks
added by the CLI have no owner, so `seed_admin` claims them for the admin user.
"""

import json
import os
import sqlite3

from werkzeug.security import generate_password_hash

from ytresearch.types import ProcessingResult, TrackAnalysis


class _SQLitePool:
    """Minimal connection factory mirroring the psycopg2 pool interface.

    SQLite needs no real pool; each `getconn()` opens a fresh connection so it
    can be used safely from the request thread or the background worker thread.
    """

    def __init__(self, path: str):
        self.path = path

    def getconn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=30,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,  # TIMESTAMP cols -> datetime
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def putconn(self, conn: sqlite3.Connection):
        conn.close()

    def closeall(self):
        pass


_pool: _SQLitePool | None = None


def _resolve_path(database_url: str) -> str:
    """Turn a sqlite:/// URL into a filesystem path.

    Accepts:
      sqlite:///~/music-archive/archive.db   -> ~ expanded
      sqlite:////absolute/path/archive.db    -> /absolute/path/archive.db
      sqlite:///relative/path.db             -> relative to cwd
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(
            "DATABASE_URL must be a sqlite:/// URL, e.g. "
            "sqlite:///~/music-archive/archive.db (got: %r)" % database_url
        )
    return os.path.expanduser(database_url[len(prefix):])


def get_pool(database_url: str) -> _SQLitePool:
    global _pool
    if _pool is None:
        _pool = _SQLitePool(_resolve_path(database_url))
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def get_conn(pool: _SQLitePool) -> sqlite3.Connection:
    return pool.getconn()


def put_conn(pool: _SQLitePool, conn: sqlite3.Connection):
    pool.putconn(conn)


# The tracks table is owned by the ytresearch CLI; this mirrors its schema so a
# fresh database (no archive yet) still works.
_TRACKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_url           TEXT UNIQUE,
    youtube_id            TEXT,
    title                 TEXT,
    artist                TEXT,
    song                  TEXT,
    year                  INTEGER,
    country               TEXT,
    language_ethnic_group TEXT,
    genre                 TEXT,
    view_count            INTEGER,
    summary               TEXT,
    summary_short         TEXT,
    uploader              TEXT,
    uploader_id           TEXT,
    upload_date           TEXT,
    duration_seconds      INTEGER,
    like_count            INTEGER,
    comment_count         INTEGER,
    description           TEXT,
    comments_json         TEXT,
    tags                  TEXT,
    categories            TEXT,
    channel_url           TEXT,
    audio_path            TEXT,
    video_path            TEXT,
    thumbnail_path        TEXT,
    downloaded_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reprocessed_at        TIMESTAMP
);
"""

_USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT UNIQUE NOT NULL,
    password_hash     TEXT NOT NULL,
    anthropic_api_key TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Workflow columns the web app needs on the shared tracks table. Existing CLI
# rows pick up the DEFAULT, so they display as completed in the UI.
_TRACKS_WEB_COLUMNS = {
    "user_id": "INTEGER",
    "status": "TEXT DEFAULT 'success'",
    "error": "TEXT",
}


def init_db(pool: _SQLitePool):
    """Create tables if needed and migrate the shared tracks table."""
    conn = get_conn(pool)
    try:
        conn.executescript(_USERS_SCHEMA)
        conn.executescript(_TRACKS_SCHEMA)

        existing = {row["name"] for row in conn.execute("PRAGMA table_info(tracks)")}
        for col, decl in _TRACKS_WEB_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} {decl}")

        conn.commit()
    finally:
        put_conn(pool, conn)


# --- User operations ---

def create_user(pool, username: str, password_hash: str) -> int:
    conn = get_conn(pool)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        put_conn(pool, conn)


def get_user_by_username(pool, username: str) -> dict | None:
    conn = get_conn(pool)
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        put_conn(pool, conn)


def get_user_by_id(pool, user_id: int) -> dict | None:
    conn = get_conn(pool)
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        put_conn(pool, conn)


# --- Track operations ---

def track_exists_for_user(pool, user_id: int, youtube_id: str) -> bool:
    conn = get_conn(pool)
    try:
        row = conn.execute(
            "SELECT 1 FROM tracks WHERE user_id = ? AND youtube_id = ? LIMIT 1",
            (user_id, youtube_id),
        ).fetchone()
        return row is not None
    finally:
        put_conn(pool, conn)


def insert_track(pool, result: ProcessingResult, comments: list[dict], user_id: int):
    """Insert a processed track into the shared archive."""
    video = result["video"]
    analysis = result.get("analysis") or {}
    conn = get_conn(pool)
    try:
        conn.execute(
            """
            INSERT INTO tracks (
                user_id, youtube_url, youtube_id, title, artist, song, year,
                country, language_ethnic_group, genre, view_count,
                summary, summary_short, uploader, uploader_id, upload_date,
                duration_seconds, like_count, comment_count, description,
                comments_json, tags, categories, channel_url, status,
                audio_path, video_path
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?
            )
            """,
            (
                user_id,
                video.get("youtube_url", ""),
                video.get("youtube_id", ""),
                video.get("title"),
                analysis.get("artist"),
                analysis.get("song"),
                analysis.get("year"),
                analysis.get("country"),
                analysis.get("language_ethnic_group"),
                analysis.get("genre"),
                video.get("view_count"),
                analysis.get("summary"),
                analysis.get("summary_short"),
                video.get("uploader"),
                video.get("uploader_id"),
                video.get("upload_date"),
                video.get("duration_seconds"),
                video.get("like_count"),
                video.get("comment_count"),
                video.get("description"),
                json.dumps(comments) if comments else None,
                json.dumps(video.get("tags", [])),
                json.dumps(video.get("categories", [])),
                video.get("channel_url"),
                result.get("status", "success"),
                result.get("audio_path"),
                result.get("video_path"),
            ),
        )
        conn.commit()
    finally:
        put_conn(pool, conn)


def delete_track(pool, user_id: int, youtube_id: str):
    """Delete a track by user_id and youtube_id."""
    conn = get_conn(pool)
    try:
        conn.execute(
            "DELETE FROM tracks WHERE user_id = ? AND youtube_id = ?",
            (user_id, youtube_id),
        )
        conn.commit()
    finally:
        put_conn(pool, conn)


def insert_pending_track(pool, user_id: int, youtube_url: str, youtube_id: str):
    """Insert a placeholder track with status='pending'."""
    conn = get_conn(pool)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO tracks (user_id, youtube_url, youtube_id, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (user_id, youtube_url, youtube_id),
        )
        conn.commit()
    finally:
        put_conn(pool, conn)


def update_track_status(pool, user_id: int, youtube_id: str, status: str, error: str | None = None):
    """Update the status (and optionally error) of a track."""
    conn = get_conn(pool)
    try:
        conn.execute(
            "UPDATE tracks SET status = ?, error = ? WHERE user_id = ? AND youtube_id = ?",
            (status, error, user_id, youtube_id),
        )
        conn.commit()
    finally:
        put_conn(pool, conn)


def update_track_analysis(pool, user_id: int, youtube_id: str, analysis: TrackAnalysis):
    """Update analysis fields on an existing track."""
    conn = get_conn(pool)
    try:
        conn.execute(
            """
            UPDATE tracks SET
                artist = ?, song = ?, year = ?, country = ?,
                language_ethnic_group = ?, genre = ?,
                summary = ?, summary_short = ?
            WHERE user_id = ? AND youtube_id = ?
            """,
            (
                analysis.get("artist"),
                analysis.get("song"),
                analysis.get("year"),
                analysis.get("country"),
                analysis.get("language_ethnic_group"),
                analysis.get("genre"),
                analysis.get("summary"),
                analysis.get("summary_short"),
                user_id,
                youtube_id,
            ),
        )
        conn.commit()
    finally:
        put_conn(pool, conn)


def _row_to_track(row: sqlite3.Row) -> dict:
    """Convert a tracks row to a dict, exposing downloaded_at as created_at."""
    track = dict(row)
    track["created_at"] = track.get("downloaded_at")
    return track


def get_tracks_for_user(pool, user_id: int) -> list[dict]:
    """Return all tracks for a user, newest first."""
    conn = get_conn(pool)
    try:
        rows = conn.execute(
            """
            SELECT id, youtube_url, youtube_id, title, artist, song, year,
                   country, language_ethnic_group, genre, view_count,
                   summary, summary_short, uploader, upload_date,
                   duration_seconds, status, error, downloaded_at
            FROM tracks
            WHERE user_id = ?
            ORDER BY downloaded_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_track(r) for r in rows]
    finally:
        put_conn(pool, conn)


def get_track(pool, user_id: int, youtube_id: str) -> dict | None:
    """Return a single track by youtube_id for a user."""
    conn = get_conn(pool)
    try:
        row = conn.execute(
            """
            SELECT id, youtube_url, youtube_id, title, artist, song, year,
                   country, language_ethnic_group, genre, view_count,
                   summary, summary_short, uploader, uploader_id, upload_date,
                   duration_seconds, like_count, comment_count, description,
                   tags, categories, channel_url, audio_path, video_path,
                   status, error, downloaded_at
            FROM tracks
            WHERE user_id = ? AND youtube_id = ?
            """,
            (user_id, youtube_id),
        ).fetchone()
        return _row_to_track(row) if row is not None else None
    finally:
        put_conn(pool, conn)


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a filename is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_track_by_filename(pool, filename: str) -> dict | None:
    """Find a track whose audio_path or video_path matches `filename`.

    Matches on basename, so callers can pass either a bare filename
    ("Song.mp3") or a full path ("/Users/.../audio/Song.mp3"). Searches the
    whole shared archive (not scoped to a user). Returns None if not found.
    """
    base = os.path.basename(filename)
    if not base:
        return None
    suffix = f"%/{_escape_like(base)}"  # path ending in "/<basename>"
    conn = get_conn(pool)
    try:
        row = conn.execute(
            """
            SELECT id, youtube_url, youtube_id, title, artist, song, year,
                   country, language_ethnic_group, genre, view_count,
                   summary, summary_short, uploader, uploader_id, upload_date,
                   duration_seconds, like_count, comment_count, description,
                   tags, categories, channel_url, audio_path, video_path,
                   status, error, downloaded_at
            FROM tracks
            WHERE audio_path = ? OR video_path = ?
               OR audio_path LIKE ? ESCAPE '\\'
               OR video_path LIKE ? ESCAPE '\\'
            ORDER BY downloaded_at DESC
            LIMIT 1
            """,
            (filename, filename, suffix, suffix),
        ).fetchone()
        return _row_to_track(row) if row is not None else None
    finally:
        put_conn(pool, conn)


def seed_admin(pool, username: str, password: str):
    """Create the admin user if missing, and claim any unowned archive tracks.

    Tracks added by the ytresearch CLI have no user_id; assign them to the admin
    so the existing archive is visible in the web UI.
    """
    existing = get_user_by_username(pool, username)
    if existing is None:
        create_user(pool, username, generate_password_hash(password))
        existing = get_user_by_username(pool, username)

    conn = get_conn(pool)
    try:
        conn.execute(
            "UPDATE tracks SET user_id = ? WHERE user_id IS NULL",
            (existing["id"],),
        )
        conn.commit()
    finally:
        put_conn(pool, conn)
