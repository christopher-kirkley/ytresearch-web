"""Tests for PostgresBackend (db.py)."""

from werkzeug.security import generate_password_hash
from ytresearch_web import db


def test_create_and_get_user(pool):
    pw_hash = generate_password_hash("testpass")
    user_id = db.create_user(pool, "testuser", pw_hash)
    assert user_id > 0

    user = db.get_user_by_id(pool, user_id)
    assert user is not None
    assert user["username"] == "testuser"

    user2 = db.get_user_by_username(pool, "testuser")
    assert user2 is not None
    assert user2["id"] == user_id


def test_get_nonexistent_user(pool):
    assert db.get_user_by_username(pool, "nobody") is None
    assert db.get_user_by_id(pool, 99999) is None


def test_insert_and_get_track(pool):
    pw_hash = generate_password_hash("p")
    user_id = db.create_user(pool, "trackuser", pw_hash)

    result = {
        "video": {
            "youtube_id": "abc123",
            "youtube_url": "https://youtube.com/watch?v=abc123",
            "title": "Test Video",
            "description": "A test",
            "uploader": "someone",
            "uploader_id": "UC123",
            "upload_date": "20240101",
            "duration_seconds": 180,
            "view_count": 1000,
            "like_count": 50,
            "comment_count": 10,
            "tags": ["music"],
            "categories": ["Music"],
            "channel_url": "https://youtube.com/c/someone",
            "thumbnail_path": None,
        },
        "analysis": {
            "artist": "Test Artist",
            "song": "Test Song",
            "year": 2024,
            "country": "US",
            "language_ethnic_group": "English",
            "genre": "Rock",
            "summary": "A test track summary.",
            "summary_short": "Test track.",
        },
        "audio_path": None,
        "video_path": None,
        "status": "success",
        "error": None,
    }

    db.insert_track(pool, result, [{"text": "great!", "likes": 5, "author": "fan", "timestamp": "1d ago"}], user_id)

    assert db.track_exists_for_user(pool, user_id, "abc123")
    assert not db.track_exists_for_user(pool, user_id, "xyz999")

    tracks = db.get_tracks_for_user(pool, user_id)
    assert len(tracks) == 1
    assert tracks[0]["title"] == "Test Video"
    assert tracks[0]["artist"] == "Test Artist"

    track = db.get_track(pool, user_id, "abc123")
    assert track is not None
    assert track["song"] == "Test Song"


def test_seed_admin(pool):
    db.seed_admin(pool, "admin", "adminpass")
    user = db.get_user_by_username(pool, "admin")
    assert user is not None
    # Calling again should not error
    db.seed_admin(pool, "admin", "adminpass")
