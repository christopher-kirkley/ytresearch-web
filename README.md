# ytresearch-web

A multi-user web frontend for [`ytresearch`](../ytresearch). Submit a YouTube URL
in the browser, and the app scrapes its metadata + top comments, sends them to
Claude for structured music-metadata analysis (artist, song, country, genre,
language/ethnic group, summary), and stores the result in PostgreSQL.

Unlike the CLI, this does **not** download audio/video — it's the analysis +
storage half of the pipeline, exposed as a per-user web service.

## How it works

1. Log in (Flask-Login, username/password).
2. Submit a YouTube URL on the dashboard.
3. The URL is cleaned, deduplicated per user, and processed in a background
   thread: `fetch_metadata` → `fetch_comments` → `analyze` (all from the
   `ytresearch` package).
4. The page polls `/status/<id>` until the track is `success` or `failed`.
5. Browse processed tracks on the dashboard; click through for detail.

### Layout

```
src/ytresearch_web/
├── app.py          # Flask app factory + routes
├── auth.py         # Flask-Login auth + login/logout
├── db.py           # PostgreSQL backend (users, tracks)
├── tasks.py        # process_url: scrape → analyze → store
├── extensions.py   # CSRF + rate limiter
└── templates/      # login, dashboard, track detail
```

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- A running PostgreSQL instance
- The sibling [`ytresearch`](../ytresearch) repo checked out (used as an editable
  dependency via `pyproject.toml`)
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

```bash
uv sync
cp .env.example .env   # then fill in the values below
```

`.env` variables:

| Variable            | Purpose                                       |
| ------------------- | --------------------------------------------- |
| `DATABASE_URL`      | PostgreSQL connection string                  |
| `ANTHROPIC_API_KEY` | Claude API key (used for analysis)            |
| `FLASK_SECRET_KEY`  | Random string for session signing             |
| `ADMIN_USERNAME`    | Seeded admin username (default `admin`)        |
| `ADMIN_PASSWORD`    | Seeded admin password (created on first boot)  |

Tables are created automatically on startup, and the admin user is seeded if
`ADMIN_PASSWORD` is set.

## Run

```bash
make run            # or: uv run flask --app ytresearch_web.app run --port 5001
```

Then open http://127.0.0.1:5001 and log in with the admin credentials from `.env`.

### The `ytresearch` dependency

`ytresearch` is pulled from GitHub (pinned in `uv.lock`), so `uv sync` works on
any machine with no local checkout. To bump it after upstream changes:

```bash
uv lock --upgrade-package ytresearch
```

To develop `ytresearch` and `ytresearch-web` side-by-side, set `YTRESEARCH_SRC`
to a local checkout (export it, or add it to `.env`). `make run` / `make test`
then layer that checkout in as an editable install, overriding the GitHub
version without touching `pyproject.toml` or `uv.lock`:

```bash
YTRESEARCH_SRC=/path/to/ytresearch make run
```

> Port 5000 is often taken (macOS AirPlay, and others) — use 5001. `make run`
> is the Flask dev server (auto-reload). For an always-on server use `make
> serve` (waitress) or the launchd service below.

## Run as a background service (macOS)

Runs the app via waitress on every login, bound to `127.0.0.1:5001`, and
restarts it if it crashes (a per-user launchd LaunchAgent):

```bash
uv sync                 # ensure .venv exists
make install-service    # render plist, load + start it
make service-status     # state = running, pid = …
make service-logs       # tail the log
make uninstall-service  # stop + remove
```

The plist is rendered from `deploy/ytresearch-web.plist.template` with this
checkout's absolute paths and a `PATH` that includes the venv and Homebrew (so
downloads find `yt-dlp`/`ffmpeg`). It loads config from `.env` via the working
directory. The app stays Flask — to deploy on the web later, keep waitress
bound to `127.0.0.1`, add a reverse proxy (nginx/Caddy) for TLS, set
`ALLOWED_HOSTS` to your domain, and turn `SEARCH_API_TOKEN` back on.

> Security: the app rejects requests whose `Host` header isn't localhost (a
> DNS-rebinding guard). Set `ALLOWED_HOSTS=your.domain,…` to allow others.

## Search API (for scripting / Automator)

`GET /search` looks up a track by its audio/video **filename** and returns JSON.
Unlike the dashboard, it is not gated by interactive login, so it works from
scripts. Access is restricted to **localhost**. A token is optional: it works
with no token; set `SEARCH_API_TOKEN` in `.env` to additionally require one
(sent via `?token=` or the `X-API-Key` header).

```bash
# bare filename or full path both work
curl 'http://127.0.0.1:5001/search?filename=Song.mp3'
curl 'http://127.0.0.1:5001/search?filename=/Users/you/music-archive/audio/Song.mp3'
# with a token configured:
curl -H "X-API-Key: YOUR_TOKEN" 'http://127.0.0.1:5001/search?filename=Song.mp3'
```

Responses: `200` with the record as JSON, `404` if no match, `400` if
`filename` is missing, `403` if not from localhost, `401` if a token is
configured but missing/invalid.

## Finder Quick Action (open a file's detail page)

`scripts/ytresearch-lookup.sh` opens the **detail page** for an archive file
selected in Finder. It looks the file up by its full path in the SQLite archive
to get the track's `youtube_id`, then opens `/track/<id>` — works for both
`.mp3` and `.mp4`, and the id is unique so there's never any filename ambiguity.

Set it up:

1. Automator → **New → Quick Action**.
2. "Workflow receives current **files or folders** in **Finder**".
3. Add **Run Shell Script**, set **Pass input: as arguments**.
4. Paste the body of `scripts/ytresearch-lookup.sh`.

It then appears in Finder's right-click **Quick Actions** for selected files.
The detail page needs you logged into the app in your browser (you'll be sent
through `/login` and on to the page if not).

> Going through the id (`/track/<id>`) opens the real detail **page**; hitting
> `/search` directly returns JSON instead.

## Tests

No external database needed — tests run against a throwaway SQLite db:

```bash
make test           # or: uv run pytest
```

`make test` honors `YTRESEARCH_SRC` the same way `make run` does.

Frontend search/sort helpers (Node's built-in runner, no dependencies):

```bash
node --test "tests/js/*.test.js"
```
