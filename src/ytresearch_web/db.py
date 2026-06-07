"""PostgreSQL database backend for ytresearch-web."""

import json

import psycopg2
import psycopg2.pool
from werkzeug.security import generate_password_hash

from ytresearch.types import ProcessingResult, TrackAnalysis


_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pool(database_url: str) -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 5, database_url)
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


def get_conn(pool: psycopg2.pool.ThreadedConnectionPool):
    return pool.getconn()


def put_conn(pool: psycopg2.pool.ThreadedConnectionPool, conn):
    pool.putconn(conn)


def init_db(pool: psycopg2.pool.ThreadedConnectionPool):
    """Create tables if they don't exist."""
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    anthropic_api_key TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS tracks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    youtube_url TEXT NOT NULL,
                    youtube_id TEXT NOT NULL,
                    title TEXT,
                    artist TEXT,
                    song TEXT,
                    year INTEGER,
                    country TEXT,
                    language_ethnic_group TEXT,
                    genre TEXT,
                    view_count INTEGER,
                    summary TEXT,
                    summary_short TEXT,
                    uploader TEXT,
                    uploader_id TEXT,
                    upload_date TEXT,
                    duration_seconds INTEGER,
                    like_count INTEGER,
                    comment_count INTEGER,
                    description TEXT,
                    comments_json TEXT,
                    tags TEXT,
                    categories TEXT,
                    channel_url TEXT,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    audio_path TEXT,
                    video_path TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, youtube_id)
                );

                ALTER TABLE tracks ADD COLUMN IF NOT EXISTS audio_path TEXT;
                ALTER TABLE tracks ADD COLUMN IF NOT EXISTS video_path TEXT;
            """)
        conn.commit()
    finally:
        put_conn(pool, conn)


# --- User operations ---

def create_user(pool, username: str, password_hash: str) -> int:
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                (username, password_hash),
            )
            user_id = cur.fetchone()[0]
        conn.commit()
        return user_id
    finally:
        put_conn(pool, conn)


def get_user_by_username(pool, username: str) -> dict | None:
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {"id": row[0], "username": row[1], "password_hash": row[2], "created_at": row[3]}
    finally:
        put_conn(pool, conn)


def get_user_by_id(pool, user_id: int) -> dict | None:
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {"id": row[0], "username": row[1], "password_hash": row[2], "created_at": row[3]}
    finally:
        put_conn(pool, conn)


# --- Track operations ---

def track_exists_for_user(pool, user_id: int, youtube_id: str) -> bool:
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM tracks WHERE user_id = %s AND youtube_id = %s",
                (user_id, youtube_id),
            )
            return cur.fetchone() is not None
    finally:
        put_conn(pool, conn)


def insert_track(pool, result: ProcessingResult, comments: list[dict], user_id: int):
    """Insert a processed track into the database."""
    video = result["video"]
    analysis = result.get("analysis") or {}
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tracks (
                    user_id, youtube_url, youtube_id, title, artist, song, year,
                    country, language_ethnic_group, genre, view_count,
                    summary, summary_short, uploader, uploader_id, upload_date,
                    duration_seconds, like_count, comment_count, description,
                    comments_json, tags, categories, channel_url, status,
                    audio_path, video_path
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s
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
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM tracks WHERE user_id = %s AND youtube_id = %s",
                (user_id, youtube_id),
            )
        conn.commit()
    finally:
        put_conn(pool, conn)


def insert_pending_track(pool, user_id: int, youtube_url: str, youtube_id: str):
    """Insert a placeholder track with status='pending'."""
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tracks (user_id, youtube_url, youtube_id, status)
                VALUES (%s, %s, %s, 'pending')
                ON CONFLICT (user_id, youtube_id) DO NOTHING
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
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tracks SET status = %s, error = %s WHERE user_id = %s AND youtube_id = %s",
                (status, error, user_id, youtube_id),
            )
        conn.commit()
    finally:
        put_conn(pool, conn)


def update_track_analysis(pool, user_id: int, youtube_id: str, analysis: TrackAnalysis):
    """Update analysis fields on an existing track."""
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks SET
                    artist = %s, song = %s, year = %s, country = %s,
                    language_ethnic_group = %s, genre = %s,
                    summary = %s, summary_short = %s
                WHERE user_id = %s AND youtube_id = %s
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


def get_tracks_for_user(pool, user_id: int) -> list[dict]:
    """Return all tracks for a user, newest first."""
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, youtube_url, youtube_id, title, artist, song, year,
                       country, language_ethnic_group, genre, view_count,
                       summary, summary_short, uploader, upload_date,
                       duration_seconds, status, error, created_at
                FROM tracks
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        put_conn(pool, conn)


def get_track(pool, user_id: int, youtube_id: str) -> dict | None:
    """Return a single track by youtube_id for a user."""
    conn = get_conn(pool)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, youtube_url, youtube_id, title, artist, song, year,
                       country, language_ethnic_group, genre, view_count,
                       summary, summary_short, uploader, uploader_id, upload_date,
                       duration_seconds, like_count, comment_count, description,
                       tags, categories, channel_url, audio_path, video_path, status, error, created_at
                FROM tracks
                WHERE user_id = %s AND youtube_id = %s
                """,
                (user_id, youtube_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))
    finally:
        put_conn(pool, conn)


def seed_admin(pool, username: str, password: str):
    """Create admin user if it doesn't exist."""
    existing = get_user_by_username(pool, username)
    if existing is None:
        pw_hash = generate_password_hash(password)
        create_user(pool, username, pw_hash)
