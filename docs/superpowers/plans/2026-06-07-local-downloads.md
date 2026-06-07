# Opt-In Local Downloads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the web app optionally download + tag media (MP3 + MP4) to pre-existing local directories, gated by env config, never creating dirs or overwriting files.

**Architecture:** A new focused `download.py` module holds env-gated config helpers and safety-honoring yt-dlp wrappers (validate dir, `--no-overwrites`, no `mkdir`), reusing the sibling CLI's `tagger` for ID3/artwork. `tasks.py` calls it at process time inside the existing background thread; `db.py` gains `audio_path`/`video_path` columns; `app.py` + templates expose a per-request, capability-gated download control.

**Tech Stack:** Flask/Jinja, psycopg2/PostgreSQL, yt-dlp + ffmpeg (system deps from the `ytresearch` package), `ytresearch.tagger` (mutagen), pytest (mocked subprocess — no network).

---

## File Structure

- **Create:** `src/ytresearch_web/download.py` — config gating + yt-dlp wrappers + `archive_track` orchestration.
- **Create:** `tests/test_download.py` — unit tests (subprocess + tagger mocked; tmp dirs; no network, no DB).
- **Modify:** `src/ytresearch_web/db.py` — schema migration + persist/return the two path columns.
- **Modify:** `tests/test_db.py` — path round-trip test.
- **Modify:** `src/ytresearch_web/tasks.py` — `process_url(..., download, include_video)`.
- **Modify:** `tests/test_tasks.py` — download path test.
- **Modify:** `src/ytresearch_web/app.py` — import download; pass `downloads_enabled` to template; parse + validate download fields in `/process`.
- **Modify:** `src/ytresearch_web/templates/dashboard.html` — capability-gated download checkbox + select; send fields in the existing fetch.
- **Modify:** `src/ytresearch_web/templates/track.html` — show saved file paths.
- **Modify:** `.env.example` — document the two vars (commented out).

**Testing note (read before starting):** Tests in `test_db.py`/`test_tasks.py` use the `pool` fixture, which **skips** unless `TEST_DATABASE_URL` is set. Do NOT point `TEST_DATABASE_URL` at the app's real database (the fixture deletes all rows). The `download.py` tests need no DB and run always. For each DB-touching task, "tests pass" means: the suite runs with **no failures and no errors** (DB tests may show as skipped). If a disposable Postgres test DB is available, set `TEST_DATABASE_URL` to exercise them fully.

---

## Task 1: Download config gating + dir validation

**Files:**
- Create: `src/ytresearch_web/download.py`
- Create: `tests/test_download.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_download.py`:

```python
"""Tests for ytresearch_web.download (no network; subprocess/tagger mocked)."""

from pathlib import Path

import pytest

from ytresearch_web import download
from ytresearch_web.download import DownloadError


def test_get_download_dirs_none_when_unset(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_AUDIO_DIR", raising=False)
    monkeypatch.delenv("DOWNLOAD_VIDEO_DIR", raising=False)
    assert download.get_download_dirs() is None


def test_get_download_dirs_returns_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("DOWNLOAD_AUDIO_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("DOWNLOAD_VIDEO_DIR", str(tmp_path / "v"))
    assert download.get_download_dirs() == (tmp_path / "a", tmp_path / "v")


def test_downloads_enabled_requires_existing_dirs(monkeypatch, tmp_path):
    a, v = tmp_path / "audio", tmp_path / "video"
    monkeypatch.setenv("DOWNLOAD_AUDIO_DIR", str(a))
    monkeypatch.setenv("DOWNLOAD_VIDEO_DIR", str(v))
    assert download.downloads_enabled() is False
    a.mkdir()
    v.mkdir()
    assert download.downloads_enabled() is True


def test_validate_dir_raises_and_does_not_create(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(DownloadError):
        download._validate_dir(missing)
    assert not missing.exists()


def test_validate_dir_returns_existing(tmp_path):
    assert download._validate_dir(tmp_path) == tmp_path
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_download.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'ytresearch_web.download'`.

- [ ] **Step 3: Implement the config/validation portion of the module**

Create `src/ytresearch_web/download.py`:

```python
"""Optional local media downloads (audio/video) via yt-dlp.

Gated by environment config and OFF by default. Never creates directories and
never overwrites existing files.
"""

import logging
import os
import subprocess
from pathlib import Path

from ytresearch import tagger
from ytresearch.types import TrackAnalysis, VideoMetadata

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when a download cannot proceed or fails."""


def get_download_dirs() -> tuple[Path, Path] | None:
    """Return (audio_dir, video_dir) from env, or None if either is unset."""
    audio = os.environ.get("DOWNLOAD_AUDIO_DIR")
    video = os.environ.get("DOWNLOAD_VIDEO_DIR")
    if not audio or not video:
        return None
    return Path(audio), Path(video)


def _is_writable_dir(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def downloads_enabled() -> bool:
    """True only if both dirs are configured and are existing, writable dirs."""
    dirs = get_download_dirs()
    if dirs is None:
        return False
    return all(_is_writable_dir(d) for d in dirs)


def _validate_dir(path: Path) -> Path:
    """Return path if it is an existing writable directory, else raise.

    Never creates the directory.
    """
    if not _is_writable_dir(path):
        raise DownloadError(
            f"Download directory is not an existing writable directory: {path}"
        )
    return path
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_download.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ytresearch_web/download.py tests/test_download.py
git commit -m "Add download config gating and dir validation"
```

---

## Task 2: yt-dlp download wrappers (no-create, no-overwrite)

**Files:**
- Modify: `src/ytresearch_web/download.py`
- Modify: `tests/test_download.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_download.py`:

```python
from unittest.mock import MagicMock, patch


def _ok(stdout):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


def _fail(stderr="boom"):
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = stderr
    return m


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_uses_no_overwrites_and_returns_path(mock_run, tmp_path):
    mock_run.return_value = _ok(str(tmp_path / "Song.mp3"))
    path = download.download_audio("URL", tmp_path)
    assert path == Path(tmp_path / "Song.mp3")
    argv = mock_run.call_args[0][0]
    assert argv[0] == "yt-dlp"
    assert "--no-overwrites" in argv


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_raises_on_failure(mock_run, tmp_path):
    mock_run.return_value = _fail("nope")
    with pytest.raises(DownloadError):
        download.download_audio("URL", tmp_path)


@patch("ytresearch_web.download.subprocess.run")
def test_download_audio_validates_dir_before_running(mock_run, tmp_path):
    with pytest.raises(DownloadError):
        download.download_audio("URL", tmp_path / "missing")
    mock_run.assert_not_called()


@patch("ytresearch_web.download.subprocess.run")
def test_download_video_uses_no_overwrites_and_returns_path(mock_run, tmp_path):
    mock_run.return_value = _ok(str(tmp_path / "Song.mp4"))
    path = download.download_video("URL", tmp_path)
    assert path == Path(tmp_path / "Song.mp4")
    assert "--no-overwrites" in mock_run.call_args[0][0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_download.py -v`
Expected: FAIL — `AttributeError: module 'ytresearch_web.download' has no attribute 'download_audio'`.

- [ ] **Step 3: Add the wrapper functions to `download.py`**

Append to `src/ytresearch_web/download.py`:

```python
def _run_yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def download_audio(url: str, audio_dir: Path) -> Path:
    """Download best audio as MP3 into audio_dir. Never overwrites."""
    _validate_dir(audio_dir)
    output_template = str(audio_dir / "%(title)s.%(ext)s")
    result = _run_yt_dlp([
        "yt-dlp",
        "-f", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-overwrites",
        "-o", output_template,
        "--print", "after_move:filepath",
        url,
    ])
    if result.returncode != 0:
        raise DownloadError(f"Audio download failed: {result.stderr.strip()}")
    return Path(result.stdout.strip().splitlines()[-1])


def download_video(url: str, video_dir: Path) -> Path:
    """Download best video+audio merged as MP4 into video_dir. Never overwrites."""
    _validate_dir(video_dir)
    output_template = str(video_dir / "%(title)s.%(ext)s")
    result = _run_yt_dlp([
        "yt-dlp",
        "-f", "bestvideo+bestaudio",
        "--merge-output-format", "mp4",
        "--no-overwrites",
        "-o", output_template,
        "--print", "after_move:filepath",
        url,
    ])
    if result.returncode != 0:
        raise DownloadError(f"Video download failed: {result.stderr.strip()}")
    return Path(result.stdout.strip().splitlines()[-1])


def download_thumbnail(url: str, audio_dir: Path) -> Path | None:
    """Download the thumbnail as jpg into audio_dir. Best-effort; never overwrites."""
    _validate_dir(audio_dir)
    output_template = str(audio_dir / "%(title)s.%(ext)s")
    result = _run_yt_dlp([
        "yt-dlp",
        "--write-thumbnail",
        "--skip-download",
        "--convert-thumbnails", "jpg",
        "--no-overwrites",
        "-o", output_template,
        url,
    ])
    if result.returncode != 0:
        logger.warning("Thumbnail download failed for %s", url)
        return None
    for f in audio_dir.iterdir():
        if f.suffix == ".jpg":
            return f
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_download.py -v`
Expected: PASS — 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ytresearch_web/download.py tests/test_download.py
git commit -m "Add no-overwrite yt-dlp download wrappers"
```

---

## Task 3: `archive_track` orchestration

**Files:**
- Modify: `src/ytresearch_web/download.py`
- Modify: `tests/test_download.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_download.py`:

```python
_META = {"view_count": 1234}
_ANALYSIS = {
    "artist": "A", "song": "S", "year": 2024, "country": "C",
    "language_ethnic_group": "L", "genre": "G", "summary": "x", "summary_short": "y",
}


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_audio_only_skips_video(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=False)
    assert out["audio_path"] == str(tmp_path / "Song.mp3")
    assert out["video_path"] is None
    mock_video.assert_not_called()
    mock_tagger.write_tags.assert_called_once()


@patch("ytresearch_web.download.download_video")
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_with_video(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    mock_video.return_value = tmp_path / "Song.mp4"
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=True)
    assert out["video_path"] == str(tmp_path / "Song.mp4")
    mock_video.assert_called_once()


@patch("ytresearch_web.download.download_video", side_effect=DownloadError("fail"))
@patch("ytresearch_web.download.tagger")
@patch("ytresearch_web.download.download_thumbnail", return_value=None)
@patch("ytresearch_web.download.download_audio")
def test_archive_track_tolerates_video_failure(mock_audio, mock_thumb, mock_tagger, mock_video, tmp_path):
    mock_audio.return_value = tmp_path / "Song.mp3"
    out = download.archive_track("URL", _META, _ANALYSIS, tmp_path, tmp_path, include_video=True)
    assert out["video_path"] is None
    assert out["audio_path"] == str(tmp_path / "Song.mp3")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_download.py -v`
Expected: FAIL — `AttributeError: module 'ytresearch_web.download' has no attribute 'archive_track'`.

- [ ] **Step 3: Add `archive_track` to `download.py`**

Append to `src/ytresearch_web/download.py`:

```python
def archive_track(
    url: str,
    metadata: VideoMetadata,
    analysis: TrackAnalysis | None,
    audio_dir: Path,
    video_dir: Path,
    include_video: bool = True,
) -> dict:
    """Download + tag audio (and optionally video).

    Returns {"audio_path": str, "video_path": str | None}. An audio failure
    raises DownloadError; a video failure is logged and tolerated.
    """
    audio_path = download_audio(url, audio_dir)

    thumb = download_thumbnail(url, audio_dir)
    if thumb is not None:
        tagger.embed_thumbnail(audio_path, thumb)
        thumb.unlink(missing_ok=True)

    if analysis is not None:
        tagger.write_tags(audio_path, analysis, metadata.get("view_count", 0) or 0)

    video_path: Path | None = None
    if include_video:
        try:
            video_path = download_video(url, video_dir)
        except DownloadError as e:
            logger.warning("Video download failed (continuing): %s", e)

    return {
        "audio_path": str(audio_path),
        "video_path": str(video_path) if video_path else None,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_download.py -v`
Expected: PASS — 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ytresearch_web/download.py tests/test_download.py
git commit -m "Add archive_track orchestration with tagging and optional video"
```

---

## Task 4: DB schema migration + persist/return paths

**Files:**
- Modify: `src/ytresearch_web/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db.py`:

```python
def test_track_paths_round_trip(pool):
    user_id = db.create_user(pool, "pathuser", generate_password_hash("p"))
    result = {
        "video": {
            "youtube_id": "pth1", "youtube_url": "u", "title": "T", "description": "",
            "uploader": "", "uploader_id": "", "upload_date": "", "duration_seconds": 0,
            "view_count": 0, "like_count": 0, "comment_count": 0,
            "tags": [], "categories": [], "channel_url": "", "thumbnail_path": None,
        },
        "analysis": None,
        "audio_path": "/music/audio/Song.mp3",
        "video_path": "/music/video/Song.mp4",
        "status": "success",
        "error": None,
    }
    db.insert_track(pool, result, [], user_id)
    track = db.get_track(pool, user_id, "pth1")
    assert track["audio_path"] == "/music/audio/Song.mp3"
    assert track["video_path"] == "/music/video/Song.mp4"
```

- [ ] **Step 2: Run the test to verify it fails (or skips without a DB)**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_db.py::test_track_paths_round_trip -v`
Expected without `TEST_DATABASE_URL`: SKIPPED (the `pool` fixture skips). With a disposable `TEST_DATABASE_URL`: FAIL — `KeyError: 'audio_path'` (column not selected/stored yet). Either way, proceed to implement.

- [ ] **Step 3a: Add columns + migration in `init_db`**

In `src/ytresearch_web/db.py`, inside `init_db`, find:

```python
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, youtube_id)
                );
            """)
```
Replace with:

```python
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
```

- [ ] **Step 3b: Persist the paths in `insert_track`**

In `insert_track`, find the column list and VALUES placeholders:

```python
                    comments_json, tags, categories, channel_url, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
```
Replace with:

```python
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
```

Then find the end of the values tuple:

```python
                    video.get("channel_url"),
                    result.get("status", "success"),
                ),
            )
```
Replace with:

```python
                    video.get("channel_url"),
                    result.get("status", "success"),
                    result.get("audio_path"),
                    result.get("video_path"),
                ),
            )
```

- [ ] **Step 3c: Return the paths from `get_track`**

In `get_track`, find:

```python
                       tags, categories, channel_url, status, error, created_at
```
Replace with:

```python
                       tags, categories, channel_url, audio_path, video_path, status, error, created_at
```

- [ ] **Step 4: Run the test to verify it passes (or skips cleanly)**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_db.py -v`
Expected: with a test DB, `test_track_paths_round_trip` PASSES; without one, all DB tests SKIP. In both cases there must be NO failures and NO collection/import errors.

- [ ] **Step 5: Commit**

```bash
git add src/ytresearch_web/db.py tests/test_db.py
git commit -m "Add audio_path/video_path columns, migration, and round-trip"
```

---

## Task 5: Wire downloads into `process_url`

**Files:**
- Modify: `src/ytresearch_web/tasks.py`
- Modify: `tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_tasks.py`, add `from pathlib import Path` near the top imports if not present, then append:

```python
@patch("ytresearch_web.download.archive_track",
       return_value={"audio_path": "/a/Song.mp3", "video_path": "/v/Song.mp4"})
@patch("ytresearch_web.download.get_download_dirs", return_value=(Path("/a"), Path("/v")))
@patch("ytresearch_web.tasks.analyze", return_value=MOCK_ANALYSIS)
@patch("ytresearch_web.tasks.fetch_comments", return_value=MOCK_COMMENTS)
@patch("ytresearch_web.tasks.fetch_metadata", return_value=MOCK_METADATA)
@patch("ytresearch_web.tasks.extract_video_id", return_value="mock123")
def test_process_url_with_download(mock_extract, mock_meta, mock_comments, mock_analyze, mock_dirs, mock_archive, pool):
    user_id = db.create_user(pool, "dluser", generate_password_hash("p"))
    result = process_url(
        "https://youtube.com/watch?v=mock123", user_id, pool,
        download=True, include_video=True,
    )
    assert result is not None
    assert result["audio_path"] == "/a/Song.mp3"
    assert result["video_path"] == "/v/Song.mp4"
    mock_archive.assert_called_once()
    track = db.get_track(pool, user_id, "mock123")
    assert track["audio_path"] == "/a/Song.mp3"
```

- [ ] **Step 2: Run the test to verify it fails (or skips without a DB)**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_tasks.py -v`
Expected without `TEST_DATABASE_URL`: SKIPPED. With a test DB: FAIL — `process_url()` got an unexpected keyword argument `download`.

- [ ] **Step 3: Update `process_url`**

In `src/ytresearch_web/tasks.py`, replace the function signature:

```python
def process_url(
    url: str,
    user_id: int,
    pool,
    model: str = "claude-sonnet-4-6",
    comment_limit: int = 100,
) -> ProcessingResult | None:
```
with:

```python
def process_url(
    url: str,
    user_id: int,
    pool,
    model: str = "claude-sonnet-4-6",
    comment_limit: int = 100,
    download: bool = False,
    include_video: bool = True,
) -> ProcessingResult | None:
```

Then find the result-building block:

```python
        analysis = analyze(metadata, comments, model=model)

        result: ProcessingResult = {
            "video": metadata,
            "analysis": analysis,
            "audio_path": None,
            "video_path": None,
            "status": "success",
            "error": None,
        }
```
Replace with:

```python
        analysis = analyze(metadata, comments, model=model)

        audio_path = None
        video_path = None
        if download:
            from . import download as dl

            dirs = dl.get_download_dirs()
            if dirs is None:
                raise dl.DownloadError("Downloads are not configured.")
            audio_dir, video_dir = dirs
            paths = dl.archive_track(
                url, metadata, analysis, audio_dir, video_dir,
                include_video=include_video,
            )
            audio_path = paths["audio_path"]
            video_path = paths["video_path"]

        result: ProcessingResult = {
            "video": metadata,
            "analysis": analysis,
            "audio_path": audio_path,
            "video_path": video_path,
            "status": "success",
            "error": None,
        }
```

(The existing `except Exception` already sets status `failed` and re-raises, so an audio `DownloadError` correctly marks the track failed.)

- [ ] **Step 4: Run the test to verify it passes (or skips cleanly)**

Run: `cd /home/chris/Documents/ytresearch-web && uv run pytest tests/test_tasks.py -v`
Expected: with a test DB, `test_process_url_with_download` PASSES and `test_process_url` (no download) still PASSES; without a DB, both SKIP. No failures, no errors.

- [ ] **Step 5: Commit**

```bash
git add src/ytresearch_web/tasks.py tests/test_tasks.py
git commit -m "Wire optional downloads into process_url"
```

---

## Task 6: Route + app wiring

**Files:**
- Modify: `src/ytresearch_web/app.py`

No automated test (route requires login + DB; verified manually in Task 7). Make the edits carefully.

- [ ] **Step 1: Import the download module**

In `src/ytresearch_web/app.py`, find:

```python
from . import db
from .auth import auth_bp, login_manager
from .extensions import csrf, limiter
from .tasks import process_url
```
Replace with:

```python
from . import db
from . import download
from .auth import auth_bp, login_manager
from .extensions import csrf, limiter
from .tasks import process_url
```

- [ ] **Step 2: Pass capability flag to the dashboard template**

Find:

```python
    @app.route("/")
    @login_required
    def dashboard():
        tracks = db.get_tracks_for_user(pool, current_user.id)
        return render_template("dashboard.html", tracks=tracks)
```
Replace with:

```python
    @app.route("/")
    @login_required
    def dashboard():
        tracks = db.get_tracks_for_user(pool, current_user.id)
        return render_template(
            "dashboard.html",
            tracks=tracks,
            downloads_enabled=download.downloads_enabled(),
        )
```

- [ ] **Step 3: Parse + validate download fields in `/process`**

Find:

```python
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
```
Replace with:

```python
        if db.track_exists_for_user(pool, current_user.id, video_id):
            return jsonify({"error": "This video has already been processed."}), 409

        download_flag = request.form.get("download") in ("1", "true", "on", "yes")
        if download_flag and not download.downloads_enabled():
            return jsonify({"error": "Downloads are not configured on this server."}), 400
        include_video = request.form.get("include_video", "both") == "both"

        # Insert pending row and kick off processing in a background thread
        db.insert_pending_track(pool, current_user.id, url, video_id)
        user_id = current_user.id

        def _run():
            try:
                process_url(
                    url, user_id, pool,
                    download=download_flag, include_video=include_video,
                )
            except Exception:
                pass  # status already set to 'failed' by process_url

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"youtube_id": video_id, "status": "pending"})
```

- [ ] **Step 4: Verify the app imports cleanly**

Run:
```bash
cd /home/chris/Documents/ytresearch-web && uv run python -c "import ytresearch_web.app, ytresearch_web.download; print('imports OK')"
```
Expected: `imports OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ytresearch_web/app.py
git commit -m "Expose download capability and parse download options in route"
```

---

## Task 7: UI controls, detail paths, and .env.example

**Files:**
- Modify: `src/ytresearch_web/templates/dashboard.html`
- Modify: `src/ytresearch_web/templates/track.html`
- Modify: `.env.example`

- [ ] **Step 1: Add capability-gated download controls to the process form**

In `src/ytresearch_web/templates/dashboard.html`, find:

```html
<form id="process-form">
    <input type="hidden" id="csrf-token" value="{{ csrf_token() }}">
    <div class="form-row">
        <input type="text" name="url" id="url-input" placeholder="https://www.youtube.com/watch?v=..." required>
        <button type="submit" id="submit-btn">Process</button>
    </div>
</form>
```
Replace with:

```html
<form id="process-form">
    <input type="hidden" id="csrf-token" value="{{ csrf_token() }}">
    <div class="form-row">
        <input type="text" name="url" id="url-input" placeholder="https://www.youtube.com/watch?v=..." required>
        <button type="submit" id="submit-btn">Process</button>
    </div>
    {% if downloads_enabled %}
    <div class="form-row" style="align-items: center; gap: 0.75rem;">
        <label style="display: flex; align-items: center; gap: 0.35rem;">
            <input type="checkbox" id="download-checkbox" name="download" value="1"> ⬇ Download to disk
        </label>
        <select id="include-video-select" name="include_video">
            <option value="both">Audio + video</option>
            <option value="audio">Audio only</option>
        </select>
    </div>
    {% endif %}
</form>
```

- [ ] **Step 2: Send the download fields in the existing fetch**

In the same file, find (inside the process-form `<script>`):

```javascript
        const csrfToken = document.getElementById('csrf-token').value;
        const formData = new FormData();
        formData.append('url', url);
        formData.append('csrf_token', csrfToken);
```
Replace with:

```javascript
        const csrfToken = document.getElementById('csrf-token').value;
        const formData = new FormData();
        formData.append('url', url);
        formData.append('csrf_token', csrfToken);

        const downloadCheckbox = document.getElementById('download-checkbox');
        if (downloadCheckbox && downloadCheckbox.checked) {
            formData.append('download', '1');
            const videoSelect = document.getElementById('include-video-select');
            formData.append('include_video', videoSelect ? videoSelect.value : 'both');
        }
```

- [ ] **Step 3: Show saved file paths on the track detail page**

In `src/ytresearch_web/templates/track.html`, find:

```html
    {% if track.summary_short %}
    <h3 style="margin-bottom: 0.5rem;">Short Summary</h3>
```
Insert this block immediately BEFORE that line:

```html
    {% if track.audio_path or track.video_path %}
    <h3 style="margin-bottom: 0.5rem;">Files</h3>
    <div style="margin-bottom: 1.5rem; color: #555;">
        {% if track.audio_path %}<div><strong>Audio:</strong> <code>{{ track.audio_path }}</code></div>{% endif %}
        {% if track.video_path %}<div><strong>Video:</strong> <code>{{ track.video_path }}</code></div>{% endif %}
    </div>
    {% endif %}

    {% if track.summary_short %}
    <h3 style="margin-bottom: 0.5rem;">Short Summary</h3>
```

- [ ] **Step 4: Document the env vars in `.env.example`**

In `.env.example`, append:

```
# Optional: enable local downloads. OFF unless BOTH are set to existing,
# writable directories. The app never creates these directories and never
# overwrites existing files.
# DOWNLOAD_AUDIO_DIR=/path/to/music-archive/audio
# DOWNLOAD_VIDEO_DIR=/path/to/music-archive/video
```

- [ ] **Step 5: Manually verify end to end**

```bash
cd /home/chris/Documents/ytresearch-web
# Confirm capability is OFF by default (no env vars): controls must be absent.
pkill -f "flask --app ytresearch_web" 2>/dev/null; sleep 1
uv run flask --app ytresearch_web.app run --port 5001 > /tmp/ytweb.log 2>&1 &
sleep 4
CJ=/tmp/dlqa.txt; rm -f $CJ
TOKEN=$(curl -s -c $CJ http://127.0.0.1:5001/login | grep -oP 'name="csrf_token" value="\K[^"]+')
curl -s -b $CJ -c $CJ -o /dev/null -d "csrf_token=$TOKEN" -d "username=admin" -d "password=admin" http://127.0.0.1:5001/login
echo "controls when OFF (expect 0):"; curl -s -b $CJ http://127.0.0.1:5001/ | grep -c "download-checkbox"

# Now turn capability ON with two real existing dirs and restart.
mkdir -p /tmp/ytarchive/audio /tmp/ytarchive/video
pkill -f "flask --app ytresearch_web" 2>/dev/null; sleep 1
DOWNLOAD_AUDIO_DIR=/tmp/ytarchive/audio DOWNLOAD_VIDEO_DIR=/tmp/ytarchive/video \
  uv run flask --app ytresearch_web.app run --port 5001 > /tmp/ytweb.log 2>&1 &
sleep 4
rm -f $CJ
TOKEN=$(curl -s -c $CJ http://127.0.0.1:5001/login | grep -oP 'name="csrf_token" value="\K[^"]+')
curl -s -b $CJ -c $CJ -o /dev/null -d "csrf_token=$TOKEN" -d "username=admin" -d "password=admin" http://127.0.0.1:5001/login
echo "controls when ON (expect 1):"; curl -s -b $CJ http://127.0.0.1:5001/ | grep -c "download-checkbox"
```
Expected: `controls when OFF` prints `0`; `controls when ON` prints `1`. (Note: `.env` must NOT set `DOWNLOAD_*` for the OFF check; the env vars are passed inline only for the ON run. Optionally, log in via the browser and process a real short YouTube URL with the box checked to confirm files land in `/tmp/ytarchive/...` and the detail page lists them.)

- [ ] **Step 6: Commit**

```bash
git add src/ytresearch_web/templates/dashboard.html src/ytresearch_web/templates/track.html .env.example
git commit -m "Add download UI controls, detail-page paths, and .env.example docs"
```

---

## Self-Review Notes

- **Spec coverage:** config gating via two env vars + `downloads_enabled()` (Task 1, 6); never-create / never-overwrite (`_validate_dir` no-mkdir + `--no-overwrites`, Tasks 1–2, tested); reuse `tagger` not CLI download fns (Task 3); audio→thumbnail→tags→optional video orchestration with audio-fail=failed / video-fail-tolerated (Tasks 3, 5); schema migration + persist + return paths (Task 4); per-request UI gated by capability + 400 when requested-but-disabled (Tasks 6–7); detail-page paths (Task 7); `.env.example` docs (Task 7); tests with subprocess/tagger mocked, no network (Tasks 1–3). All spec sections map to tasks.
- **Out of scope confirmed absent:** no browser file serving, no on-demand re-download, no per-user folders, no playlists, no dashboard status column.
- **Type/name consistency:** `download.get_download_dirs() -> tuple[Path,Path]|None`, `download.downloads_enabled() -> bool`, `download._validate_dir`, `download.download_audio/video/thumbnail`, `download.archive_track(...) -> {"audio_path","video_path"}`, and `DownloadError` are used identically across `download.py`, its tests, `tasks.py` (lazy `from . import download as dl`), and `app.py` (`from . import download`). DB columns `audio_path`/`video_path` and `ProcessingResult` keys line up across `db.py`, `tasks.py`, and the templates (`track.audio_path`/`track.video_path`). Form field names `download` and `include_video` match between `dashboard.html`, the JS, and the `/process` parsing in `app.py`; the select values `both`/`audio` map to `include_video` bool consistently.
