# Opt-In Local Downloads — Design

**Date:** 2026-06-07
**Status:** Approved (pending spec review)

## Goal

Let the web app optionally download and archive media files (tagged MP3 + a
preservation MP4) to local disk when run locally, while staying safe to run as a
multi-user web service where downloading is off.

## Why it doesn't happen today

`tasks.py::process_url` calls only `fetch_metadata`, `fetch_comments`, and
`analyze`, then hardcodes `audio_path=None, video_path=None`. The download
functions in the sibling `ytresearch` CLI package are never invoked, the
`tracks` table has no path columns, and there is no download directory config.

## Scope & constraints

- **Opt-in and gated.** Downloading is possible only when configured via the
  environment; it is off by default and safe on a shared server.
- **Never create directories.** The app must not call `mkdir`. Configured
  directories must already exist; if missing, downloading errors out.
- **Never overwrite.** yt-dlp is invoked with `--no-overwrites`; an existing
  target file is left untouched.
- **Reuse, don't fork, the CLI where safe.** The CLI's own
  `download_audio/video/thumbnail` call `mkdir` and do not pass
  `--no-overwrites`, so they are NOT reused. The CLI's `tagger` (write tags,
  embed thumbnail) operates on the already-downloaded file and IS reused. The
  `ytresearch` package is unchanged by this work.
- Single-user/local is the target use; multi-user download collisions are out of
  scope (see below).

## Configuration

Two new `.env` variables, each a full path to an already-existing directory:

| Variable             | Purpose                                  |
| -------------------- | ---------------------------------------- |
| `DOWNLOAD_AUDIO_DIR` | Existing dir for tagged MP3 + artwork    |
| `DOWNLOAD_VIDEO_DIR` | Existing dir for preservation MP4        |

**Capability rule** — `downloads_enabled()` returns true only when BOTH
variables are set AND both paths are existing, writable directories. Otherwise
downloading is disabled and the UI controls are hidden.

`.env.example` is updated to document both variables (commented out, since
downloads are off by default).

## Architecture

```
/process route (app.py)
  reads "download" + "include_video" form fields
  re-checks downloads_enabled() -> 400 if a download is requested while disabled
  -> tasks.process_url(url, user_id, pool, download=?, include_video=?)
       -> analyze (as today)
       -> if download: download.archive_track(...)
       -> store paths in ProcessingResult -> db.insert_track
```

### New module: `src/ytresearch_web/download.py`

A focused, independently testable unit. Responsibilities:

- `class DownloadError(Exception)` — raised on validation/download failure.
- `_validate_dir(path) -> Path` — return the path if it is an existing, writable
  directory; otherwise raise `DownloadError`. Never creates anything.
- `download_audio(url, audio_dir) -> Path` — yt-dlp: `bestaudio/best`,
  `--extract-audio --audio-format mp3 --audio-quality 0`, `--no-overwrites`,
  `-o "<dir>/%(title)s.%(ext)s"`, `--print after_move:filepath`. Returns the
  resulting path. Raises `DownloadError` on non-zero exit.
- `download_video(url, video_dir) -> Path` — yt-dlp: `bestvideo+bestaudio`,
  `--merge-output-format mp4`, `--no-overwrites`, same `-o`/`--print`. Returns
  path; raises on failure.
- `download_thumbnail(url, audio_dir) -> Path | None` — yt-dlp:
  `--write-thumbnail --skip-download --convert-thumbnails jpg`,
  `--no-overwrites`. Returns path or None (best-effort).
- `archive_track(url, metadata, analysis, audio_dir, video_dir, include_video)
  -> {"audio_path": str, "video_path": str | None}` — orchestrates:
  1. `audio = download_audio(url, audio_dir)`
  2. `thumb = download_thumbnail(url, audio_dir)`; if present,
     `tagger.embed_thumbnail(audio, thumb)` then delete the thumb file.
  3. `tagger.write_tags(audio, analysis, metadata["view_count"])`.
  4. if `include_video`: `video = download_video(url, video_dir)` (failure here
     is logged and tolerated → `video_path = None`).
  Returns the path dict.

All directory validation happens at the start of each download call, so a
misconfigured path fails fast without writing anything.

### `tasks.py`

- `process_url(url, user_id, pool, model=..., comment_limit=..., download=False,
  include_video=True)`.
- After analysis: if `download`, call `download.archive_track(...)` with the
  configured dirs and set `audio_path`/`video_path` on the `ProcessingResult`.
- Failure policy (mirrors the CLI): an **audio** download/validation error marks
  the track `failed` (status set, error recorded). A **video** error is logged
  and tolerated (track stays `success`, `video_path` null).

### `db.py`

- `init_db` adds an idempotent migration so existing databases gain the columns:
  `ALTER TABLE tracks ADD COLUMN IF NOT EXISTS audio_path TEXT;` and likewise
  `video_path TEXT;` (run after the `CREATE TABLE IF NOT EXISTS`).
- New `CREATE TABLE` definition also includes `audio_path TEXT, video_path TEXT`.
- `insert_track` writes `result["audio_path"]` and `result["video_path"]` (it
  already receives them in the `ProcessingResult` but currently drops them).
- `get_track` returns the two columns so the detail page can show them.

### UI

- `create_app` exposes `downloads_enabled()` to templates (passed into the
  dashboard render context as `downloads_enabled`).
- `dashboard.html`: when `downloads_enabled`, render — next to the Process
  button — a checkbox `name="download"` ("⬇ Download to disk") and a
  `<select name="include_video">` with "Audio + video" (default) and
  "Audio only". The existing fetch/poll JS sends these fields. When downloads
  are disabled, none of this renders.
- `/process` route: parse `download` (checkbox) and `include_video` (select →
  bool). If `download` is truthy but `downloads_enabled()` is false, return
  `{"error": "Downloads are not configured on this server."}, 400`.
- `track.html`: when `audio_path`/`video_path` are present, show them (the saved
  file paths) in the detail view.

## Data flow

```
user submits URL (+ download? +video?) 
  -> /process validates, inserts pending row, starts background thread
  -> process_url: status=processing -> metadata/comments/analyze
       -> [if download] archive_track: yt-dlp audio (--no-overwrites, no mkdir)
            -> embed thumbnail + write tags (CLI tagger)
            -> [if include_video] yt-dlp video
       -> insert_track with audio_path/video_path
  -> dashboard polling shows success; detail page shows saved paths
```

## Error handling

- Download requested while disabled → 400 at the route, nothing runs.
- Configured dir missing / not a dir / not writable → `DownloadError` →
  audio path marks the track `failed` with a clear message; no directories are
  created.
- Existing target file → `--no-overwrites` leaves it; yt-dlp still reports the
  path, which is recorded.
- Audio failure → `failed`. Video failure → tolerated, `success`, null video.
- Claude/scrape errors unchanged from today.

## Testing

- `download.py` (unit, subprocess + `tagger` mocked, no network):
  - `_validate_dir` raises `DownloadError` for a missing path and does NOT
    create it; returns the path for an existing writable dir.
  - `download_audio` includes `--no-overwrites` in the yt-dlp argv and returns
    the printed path; raises `DownloadError` on non-zero return.
  - `archive_track` with `include_video=False` does not call `download_video`;
    with `include_video=True` it does; tags/thumbnail are applied to the audio.
  - a video download failure is swallowed (returns `video_path=None`).
- `tasks.py` (extend existing mocked test): with `download=True`, `archive_track`
  is invoked and its paths land in the stored track; with `download=False`, it is
  not called (current behavior preserved).
- `db.py`: a track inserted with paths round-trips through `get_track`.

## Out of scope (YAGNI)

- Serving downloaded files back through the browser.
- On-demand re-download of previously processed tracks.
- Per-user download folders / multi-user collision handling. With two global
  dirs and title-based filenames, concurrent multi-user downloads could collide;
  acceptable because downloads target local single-user use. Noted, not handled.
- Playlist downloads.
- A dashboard download-status column (paths shown on the detail page only).
