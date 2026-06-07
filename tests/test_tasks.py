"""Tests for process_url with mocked scraper and analyzer."""

from unittest.mock import patch
from werkzeug.security import generate_password_hash
from ytresearch_web import db
from ytresearch_web.tasks import process_url


MOCK_METADATA = {
    "youtube_id": "mock123",
    "youtube_url": "https://youtube.com/watch?v=mock123",
    "title": "Mock Video",
    "description": "desc",
    "uploader": "uploader",
    "uploader_id": "UC000",
    "upload_date": "20240601",
    "duration_seconds": 200,
    "view_count": 5000,
    "like_count": 100,
    "comment_count": 20,
    "tags": [],
    "categories": [],
    "channel_url": "https://youtube.com/c/uploader",
    "thumbnail_path": None,
}

MOCK_COMMENTS = [{"text": "nice", "likes": 3, "author": "a", "timestamp": "2d ago"}]

MOCK_ANALYSIS = {
    "artist": "Mock Artist",
    "song": "Mock Song",
    "year": 2024,
    "country": "UK",
    "language_ethnic_group": "English",
    "genre": "Pop",
    "summary": "A mock summary.",
    "summary_short": "Mock.",
}


@patch("ytresearch_web.tasks.analyze", return_value=MOCK_ANALYSIS)
@patch("ytresearch_web.tasks.fetch_comments", return_value=MOCK_COMMENTS)
@patch("ytresearch_web.tasks.fetch_metadata", return_value=MOCK_METADATA)
@patch("ytresearch_web.tasks.extract_video_id", return_value="mock123")
def test_process_url(mock_extract, mock_meta, mock_comments, mock_analyze, pool):
    user_id = db.create_user(pool, "taskuser", generate_password_hash("p"))

    result = process_url("https://youtube.com/watch?v=mock123", user_id, pool)
    assert result is not None
    assert result["status"] == "success"
    assert result["analysis"]["artist"] == "Mock Artist"

    # Track should now exist
    assert db.track_exists_for_user(pool, user_id, "mock123")

    # Processing again should return None (duplicate)
    result2 = process_url("https://youtube.com/watch?v=mock123", user_id, pool)
    assert result2 is None
