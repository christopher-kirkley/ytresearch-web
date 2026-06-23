"""Tests for the token-authed /search endpoint (Automator/scripting)."""

from werkzeug.security import generate_password_hash

from ytresearch_web import db

TOKEN = "test-search-token"


def _insert_track(pool, youtube_id, audio_path=None, video_path=None, artist="A"):
    user_id = db.create_user(pool, f"u-{youtube_id}", generate_password_hash("p"))
    result = {
        "video": {
            "youtube_id": youtube_id,
            "youtube_url": f"https://youtube.com/watch?v={youtube_id}",
            "title": f"Title {youtube_id}",
        },
        "analysis": {"artist": artist, "song": "S"},
        "audio_path": audio_path,
        "video_path": video_path,
        "status": "success",
        "error": None,
    }
    db.insert_track(pool, result, [], user_id)


def test_search_requires_token_when_configured(client, pool, monkeypatch):
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    assert client.get("/search?filename=x.mp3").status_code == 401
    assert client.get("/search?filename=x.mp3&token=wrong").status_code == 401


def test_search_tokenless_when_unset(client, pool, monkeypatch):
    monkeypatch.delenv("SEARCH_API_TOKEN", raising=False)
    # No token configured -> localhost access is allowed (404 = reached lookup).
    assert client.get("/search?filename=missing.mp3").status_code == 404


def test_search_rejects_non_localhost(client, pool, monkeypatch):
    monkeypatch.delenv("SEARCH_API_TOKEN", raising=False)
    r = client.get(
        "/search?filename=missing.mp3",
        environ_base={"REMOTE_ADDR": "8.8.8.8"},
    )
    assert r.status_code == 403


def test_search_missing_filename(client, pool, monkeypatch):
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    assert client.get(f"/search?token={TOKEN}").status_code == 400


def test_search_by_basename(client, pool, monkeypatch):
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    _insert_track(pool, "abc123", audio_path="/Users/x/music-archive/audio/Song One.mp3")
    r = client.get(f"/search?filename=Song One.mp3&token={TOKEN}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["youtube_id"] == "abc123"
    assert body["artist"] == "A"


def test_search_by_full_path_and_video(client, pool, monkeypatch):
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    _insert_track(pool, "vid999", video_path="/Users/x/music-archive/video/Clip.mp4")
    r = client.get(
        "/search?filename=/Users/x/music-archive/video/Clip.mp4&token=" + TOKEN
    )
    assert r.status_code == 200
    assert r.get_json()["youtube_id"] == "vid999"


def test_search_header_auth(client, pool, monkeypatch):
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    _insert_track(pool, "hdr111", audio_path="/a/audio/Header.mp3")
    r = client.get("/search?filename=Header.mp3", headers={"X-API-Key": TOKEN})
    assert r.status_code == 200


def test_search_not_found(client, pool, monkeypatch):
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    r = client.get(f"/search?filename=missing.mp3&token={TOKEN}")
    assert r.status_code == 404


def test_search_no_login_required(client, pool, monkeypatch):
    """/search must not redirect to login like the dashboard routes do."""
    monkeypatch.setenv("SEARCH_API_TOKEN", TOKEN)
    r = client.get(f"/search?filename=missing.mp3&token={TOKEN}")
    assert r.status_code != 302  # not redirected to /login


def test_host_guard_rejects_spoofed_host(client, pool, monkeypatch):
    """DNS-rebinding guard: a non-local Host header is rejected app-wide."""
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    assert client.get("/login", headers={"Host": "evil.example.com"}).status_code == 403
    # localhost is fine
    assert client.get("/login", headers={"Host": "localhost:5001"}).status_code == 200


def test_host_guard_respects_allowed_hosts(client, pool, monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "music.example.com")
    assert client.get("/login", headers={"Host": "music.example.com"}).status_code == 200
    assert client.get("/login", headers={"Host": "localhost"}).status_code == 403
