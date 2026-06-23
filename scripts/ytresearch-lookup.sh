#!/bin/bash
#
# Open the ytresearch-web detail page for an archive file selected in Finder.
#
# Looks the file up by its full path in the SQLite archive to get the track's
# youtube_id, then opens /track/<id>. Works for both audio (.mp3) and video
# (.mp4) files — no embedded metadata required, because the archive already
# stores each file's path and youtube_id.
#
# Automator setup:
#   New > Quick Action
#   "Workflow receives current files or folders in Finder"
#   Add "Run Shell Script", set "Pass input: as arguments"
#   Paste this script's body.
#
# It then appears in Finder's right-click > Quick Actions for selected files.
# (The detail page requires being logged into the app in your browser; if you
# aren't, you'll be sent to the login page and then on to the detail page.)

DB="$HOME/music-archive/archive.db"
PORT=5001

for FILE in "$@"; do
  # Double single-quotes so filenames containing apostrophes are SQL-safe.
  ESC=$(printf "%s" "$FILE" | sed "s/'/''/g")
  ID=$(/usr/bin/sqlite3 "$DB" \
    "SELECT youtube_id FROM tracks WHERE audio_path='$ESC' OR video_path='$ESC' LIMIT 1;")

  if [ -n "$ID" ]; then
    open "http://localhost:$PORT/track/$ID"
  else
    osascript -e "display notification \"Not in archive: $(basename "$FILE")\" with title \"ytresearch\""
  fi
done
