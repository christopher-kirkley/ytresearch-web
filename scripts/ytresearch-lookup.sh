#!/bin/bash
#
# Open the ytresearch-web detail page for an archive file selected in Finder.
#
# Resolves the track's youtube_id two ways, in order:
#   1. The youtube_id embedded in the file's tags (via ffprobe) — works even if
#      the file was moved or renamed out of the archive. Requires the file to
#      have been tagged (new downloads are; existing files via `make backfill-ids`).
#   2. Fallback: look the file up by its full path in the SQLite archive — works
#      for any file still at its archived path, even without an embedded id.
# Then opens /track/<id>.  Works for both .mp3 and .mp4.
#
# Automator setup:
#   New > Quick Action
#   "Workflow receives current files or folders in Finder"
#   Add "Run Shell Script", set "Pass input: as arguments"
#   Paste this script's body.
#
# The detail page needs you logged into the app in your browser (you'll be sent
# through /login and on to the page if not).

DB="$HOME/music-archive/archive.db"
PORT=5001
FFPROBE=/opt/homebrew/bin/ffprobe   # Homebrew path (Automator has a minimal PATH)

for FILE in "$@"; do
  # 1. embedded youtube_id
  ID=$("$FFPROBE" -v quiet -show_entries format_tags=youtube_id \
       -of default=nw=1:nk=1 "$FILE" 2>/dev/null)

  # 2. fallback: DB lookup by full path (apostrophe-safe)
  if [ -z "$ID" ]; then
    ESC=$(printf "%s" "$FILE" | sed "s/'/''/g")
    ID=$(/usr/bin/sqlite3 "$DB" \
      "SELECT youtube_id FROM tracks WHERE audio_path='$ESC' OR video_path='$ESC' LIMIT 1;")
  fi

  if [ -n "$ID" ]; then
    open "http://localhost:$PORT/track/$ID"
  else
    osascript -e "display notification \"Not in archive: $(basename "$FILE")\" with title \"ytresearch\""
  fi
done
