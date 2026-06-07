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
        "--",
        url,
    ])
    if result.returncode != 0:
        logger.warning("Thumbnail download failed for %s", url)
        return None
    for f in audio_dir.iterdir():
        if f.suffix == ".jpg":
            return f
    return None
