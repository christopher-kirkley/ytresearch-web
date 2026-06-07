"""Shared test fixtures."""

import os
import pytest
from ytresearch_web.app import create_app
from ytresearch_web import db


@pytest.fixture
def pool():
    """Database pool connected to the test database."""
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("TEST_DATABASE_URL not set")
    p = db.get_pool(test_url)
    db.init_db(p)
    yield p
    # Clean up tables after test
    conn = db.get_conn(p)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tracks")
            cur.execute("DELETE FROM users")
        conn.commit()
    finally:
        db.put_conn(p, conn)
    db.close_pool()


@pytest.fixture
def app(pool):
    """Flask test app."""
    os.environ.setdefault("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
    application = create_app()
    application.config["TESTING"] = True
    yield application


@pytest.fixture
def client(app):
    return app.test_client()
