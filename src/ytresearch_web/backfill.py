"""Embed each track's youtube_id into its archived media files.

One-off, idempotent backfill: reads (youtube_id, audio_path, video_path) from
the archive and writes the youtube_id tag into every existing file, so files
downloaded before tagging-with-id can still be identified by their metadata.

Run with `make backfill-ids` (or `python -m ytresearch_web.backfill`).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from ytresearch.media import tagger

from . import db


def main() -> None:
    load_dotenv()
    if not hasattr(tagger, "embed_youtube_id"):
        raise SystemExit(
            "The installed ytresearch is too old (no tagger.embed_youtube_id). "
            "Update it: uv lock --upgrade-package ytresearch && uv sync"
        )
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (set it in .env)")

    pool = db.get_pool(database_url)
    conn = db.get_conn(pool)
    try:
        rows = conn.execute(
            "SELECT youtube_id, audio_path, video_path FROM tracks "
            "WHERE youtube_id IS NOT NULL AND youtube_id != ''"
        ).fetchall()
    finally:
        db.put_conn(pool, conn)

    embedded = missing = errors = 0
    for row in rows:
        yid = row["youtube_id"]
        for path_str in (row["audio_path"], row["video_path"]):
            if not path_str:
                continue
            path = Path(path_str)
            if not path.is_file():
                missing += 1
                continue
            try:
                tagger.embed_youtube_id(path, yid)
                embedded += 1
            except Exception as e:  # noqa: BLE001 - report and continue
                errors += 1
                print(f"  error: {path}: {e}")

    print(f"embedded: {embedded}  |  missing files: {missing}  |  errors: {errors}")


if __name__ == "__main__":
    main()
