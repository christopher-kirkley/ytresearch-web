#!/bin/bash
# Paste everything below into Automator > Quick Action > Run Shell Script
# (Shell: /bin/bash, Pass input: as arguments).

DB="$HOME/music-archive/archive.db"
PORT=5001
FFPROBE=/opt/homebrew/bin/ffprobe   # full path: Automator has a minimal PATH

for FILE in "$@"; do
  # 1. embedded youtube_id (survives moves/renames)
  ID=$("$FFPROBE" -v quiet -show_entries format_tags=youtube_id \
       -of default=nw=1:nk=1 "$FILE" 2>/dev/null)

  # 2. fallback: look the file up by full path in the archive DB
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
