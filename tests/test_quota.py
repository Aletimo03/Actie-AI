from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import quota
from backend.app.api import app, get_graph, get_pool
from backend.app.quota import Limits, QuotaExceeded, client_key, take

NOON = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)


@pytest.fixture
def conn(db):
    db.execute(quota.SCHEMA)
    return db


def count(conn) -> int:
    return conn.execute("SELECT count(*) FROM assessment_starts").fetchone()[0]


def test_a_client_gets_its_hourly_limit_then_waits_for_the_oldest_to_expire(conn):
    limits = Limits(per_hour=2, per_day=100)
    take(conn, "a", limits, NOON)
    take(conn, "a", limits, NOON + 10 * MINUTE)
    with pytest.raises(QuotaExceeded, match="2 new assessments an hour") as refused:
        take(conn, "a", limits, NOON + 20 * MINUTE)
    assert refused.value.retry_after == 40 * 60 + 1  # when the 12:00 one leaves the window
    assert count(conn) == 2  # a refusal is not counted

    take(conn, "b", limits, NOON + 20 * MINUTE)  # other clients are not affected
    take(conn, "a", limits, NOON + 61 * MINUTE)


def test_the_daily_cap_counts_everyone_and_resets_at_midnight_utc(conn):
    limits = Limits(per_hour=10, per_day=3)
    for client in "abc":
        take(conn, client, limits, NOON)
    with pytest.raises(QuotaExceeded, match="limit of 3 assessments today") as refused:
        take(conn, "d", limits, NOON)
    assert refused.value.retry_after == 12 * 3600 + 1
    take(conn, "d", limits, NOON + 12 * 60 * MINUTE)  # 00:00 the next day


def test_rows_older_than_a_day_are_deleted(conn):
    take(conn, "a", Limits(), NOON)
    take(conn, "b", Limits(), NOON + 25 * 60 * MINUTE)
    assert count(conn) == 1


def test_clients_are_a_keyed_hash_never_the_ip():
    key = client_key("203.0.113.7", b"secret")
    assert "203.0.113" not in key and len(key) == 32
    assert key == client_key("203.0.113.7", b"secret") != client_key("203.0.113.7", b"other")


def test_the_api_refuses_over_the_limit_with_429_and_retry_after(conn, monkeypatch):
    @contextmanager
    def connection():
        yield conn

    pool = type("Pool", (), {"connection": staticmethod(connection)})()
    app.dependency_overrides[get_pool] = lambda: pool
    graph = type("Graph", (), {"invoke": lambda *_: pytest.fail("the graph must not run")})()
    app.dependency_overrides[get_graph] = lambda: graph
    monkeypatch.setattr(quota, "Limits", lambda: Limits(per_hour=0, per_day=5))
    try:
        refused = TestClient(app).post(
            "/assessments", json={"description": "We built a tool that ranks CVs for recruiters."}
        )
    finally:
        app.dependency_overrides.clear()
    assert refused.status_code == 429 and int(refused.headers["retry-after"]) >= 1
