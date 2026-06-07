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
