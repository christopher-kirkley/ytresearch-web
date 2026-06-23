"""Shared test fixtures.

Tests run against a throwaway SQLite database in a tmp dir — no external server
and never the real ~/music-archive archive.
"""

import pytest
from ytresearch_web import db


@pytest.fixture
def pool(tmp_path, monkeypatch):
    """A fresh SQLite database for each test."""
    db_path = tmp_path / "test_archive.db"
    url = f"sqlite:///{db_path}"  # tmp_path is absolute -> sqlite:////... (absolute)
    monkeypatch.setenv("DATABASE_URL", url)
    p = db.get_pool(url)
    db.init_db(p)
    yield p
    db.close_pool()


@pytest.fixture
def app(pool, monkeypatch):
    """Flask test app bound to the test database."""
    from ytresearch_web.app import create_app

    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
