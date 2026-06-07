"""URL processing: scrape, analyze, store."""

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from ytresearch.youtube import extract_video_id, fetch_metadata, fetch_comments
from ytresearch.analyzer import analyze
from ytresearch.types import ProcessingResult

from . import db


def clean_youtube_url(url: str) -> str:
    """Strip playlist/index params, keeping only the video ID."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    video_id = params.get("v", [None])[0]
    if video_id:
        clean_query = urlencode({"v": video_id})
        return urlunparse(parsed._replace(query=clean_query))
    # Short URLs (youtu.be/xxx) or other formats — return as-is
    return url


def process_url(
    url: str,
    user_id: int,
    pool,
    model: str = "claude-sonnet-4-6",
    comment_limit: int = 100,
) -> ProcessingResult | None:
    """Scrape, analyze, and store a YouTube URL.

    Assumes the pending row already exists (created by the /process route).
    """
    url = clean_youtube_url(url)
    video_id = extract_video_id(url)

    try:
        db.update_track_status(pool, user_id, video_id, "processing")

        metadata = fetch_metadata(url)
        comments = fetch_comments(url, limit=comment_limit)
        analysis = analyze(metadata, comments, model=model)

        result: ProcessingResult = {
            "video": metadata,
            "analysis": analysis,
            "audio_path": None,
            "video_path": None,
            "status": "success",
            "error": None,
        }

        # Delete the pending row and insert the full one
        db.delete_track(pool, user_id, video_id)
        db.insert_track(pool, result, comments, user_id)
        return result

    except Exception as e:
        db.update_track_status(pool, user_id, video_id, "failed", str(e))
        raise
