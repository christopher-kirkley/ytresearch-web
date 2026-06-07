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
uv run flask --app ytresearch_web.app run --port 5001
```

Then open http://127.0.0.1:5001 and log in with the admin credentials from `.env`.

> Port 5000 is often taken (macOS AirPlay, and others) — use 5001. This is the
> Flask dev server; use a production WSGI server (e.g. gunicorn) and a real
> rate-limit storage backend for deployment.

## Tests

Python (database tests skip automatically when `TEST_DATABASE_URL` is unset):

```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/ytresearch_test uv run pytest
```

Frontend search/sort helpers (Node's built-in runner, no dependencies):

```bash
node --test tests/js/
```
