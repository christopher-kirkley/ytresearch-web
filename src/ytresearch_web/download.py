"""Optional local media downloads (audio/video) via yt-dlp.

Gated by environment config and OFF by default. Never creates directories and
never overwrites existing files.
"""

import logging
import os
import subprocess
from pathlib import Path

from ytresearch.media import tagger
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


# Downloads run in background daemon threads, so a hung yt-dlp would pin a
# thread forever. Cap each invocation; tune via YT_DLP_TIMEOUT (seconds).
_DEFAULT_TIMEOUT = 600


def _run_yt_dlp(args: list[str]) -> subprocess.CompletedProcess:
    timeout = int(os.environ.get("YT_DLP_TIMEOUT", _DEFAULT_TIMEOUT))
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise DownloadError(f"yt-dlp timed out after {timeout}s")


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
        "--",
        url,
    ])
    if result.returncode != 0:
        raise DownloadError(f"Audio download failed: {result.stderr.strip()}")
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise DownloadError(f"Audio download produced no output path: {url}")
    return Path(lines[-1])


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
        "--",
        url,
    ])
    if result.returncode != 0:
        raise DownloadError(f"Video download failed: {result.stderr.strip()}")
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise DownloadError(f"Video download produced no output path: {url}")
    return Path(lines[-1])


def download_thumbnail(url: str, audio_path: Path) -> Path | None:
    """Download the thumbnail as jpg next to audio_path. Best-effort; never overwrites.

    yt-dlp writes the thumbnail using the same ``%(title)s`` stem as the audio
    file, so the result is deterministic — ``audio_path`` with a ``.jpg`` suffix.
    We must not scan the directory for "any .jpg": audio_dir holds the whole
    archive, so a scan could return (and later delete) an unrelated track's art.
    """
    audio_dir = audio_path.parent
    _validate_dir(audio_dir)
    output_template = str(audio_dir / "%(title)s.%(ext)s")
    try:
        result = _run_yt_dlp([
            "yt-dlp",
            "--write-thumbnail",
            "--skip-download",
            "--convert-thumbnails", "jpg",
            "--no-overwrites",
            "-o", output_template,
            "--",
            url,
        ])
    except DownloadError as e:
        logger.warning("Thumbnail download failed for %s: %s", url, e)
        return None
    if result.returncode != 0:
        logger.warning("Thumbnail download failed for %s", url)
        return None
    thumb = audio_path.with_suffix(".jpg")
    return thumb if thumb.is_file() else None


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
    raises DownloadError; thumbnail embed and video failures are logged and
    tolerated.
    """
    audio_path = download_audio(url, audio_dir)

    thumb = download_thumbnail(url, audio_path)
    if thumb is not None:
        try:
            tagger.embed_thumbnail(audio_path, thumb)
        except Exception as e:
            logger.warning("Thumbnail embed failed (continuing): %s", e)
        finally:
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
