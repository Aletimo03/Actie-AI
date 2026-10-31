"""Cost limits: how many new assessments one client, and everyone together, may start.

Each report costs real money (about $0.002 on Claude Haiku 5.5), so a script
could drain prepaid credits in minutes. Two limits, both counted in Postgres
so they hold across processes and pods:
- per client, in a sliding hour (QUOTA_PER_HOUR, default 10);
- for everyone, per UTC day (QUOTA_PER_DAY, default 200).
Only starting an assessment counts; answering its questions does not.

A client is a keyed hash of its IP (HMAC with QUOTA_SECRET), never the IP:
a plain hash of an IPv4 address is reversed by trying all 4 billion. Rows
older than a day are deleted as new ones come in. Behind a proxy, run uvicorn
with --proxy-headers so the IP is the user's, not the proxy's.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessment_starts (
    started_at timestamptz NOT NULL,
    client text NOT NULL
);
CREATE INDEX IF NOT EXISTS assessment_starts_time ON assessment_starts (started_at);
"""
LOCK = 41_725_001  # pg_advisory_xact_lock key: one count-and-insert at a time
HOUR = timedelta(hours=1)
# Without a secret every process draws its own, so a client's key differs per pod and
# restart: fine on a laptop, but set QUOTA_SECRET wherever more than one process runs.
SECRET = os.environ.get("QUOTA_SECRET", "").encode() or os.urandom(32)


@dataclass(frozen=True)
class Limits:
    per_hour: int = int(os.environ.get("QUOTA_PER_HOUR") or 10)
    per_day: int = int(os.environ.get("QUOTA_PER_DAY") or 200)


class QuotaExceeded(Exception):
    def __init__(self, message: str, retry_after: timedelta):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after.total_seconds()) + 1)


def client_key(ip: str, secret: bytes = SECRET) -> str:
    return hmac.new(secret, ip.encode(), hashlib.sha256).hexdigest()[:32]


def take(conn: psycopg.Connection, client: str, limits: Limits, now: datetime) -> None:
    """Count one new assessment for this client, or raise QuotaExceeded and count nothing."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        conn.execute("DELETE FROM assessment_starts WHERE started_at < %s", (now - 24 * HOUR,))
        (today,) = conn.execute(
            "SELECT count(*) FROM assessment_starts WHERE started_at >= %s", (midnight,)
        ).fetchone()
        if today >= limits.per_day:
            raise QuotaExceeded(
                f"the service has reached its limit of {limits.per_day} assessments today",
                midnight + 24 * HOUR - now,
            )
        recent = conn.execute(
            "SELECT started_at FROM assessment_starts WHERE client = %s AND started_at > %s "
            "ORDER BY started_at",
            (client, now - HOUR),
        ).fetchall()
        if len(recent) >= limits.per_hour:
            raise QuotaExceeded(
                f"limit of {limits.per_hour} new assessments an hour reached",
                # When the oldest leaves the window; a limit of 0 (service paused) has none.
                (recent[0][0] if recent else now) + HOUR - now,
            )
        conn.execute(
            "INSERT INTO assessment_starts (started_at, client) VALUES (%s, %s)", (now, client)
        )


def now() -> datetime:
    return datetime.now(UTC)
