"""Delete assessments nobody has touched for N days (default 30, RETENTION_DAYS).

A checkpoint holds the description and every answer, which may be confidential product
plans: they are kept only as long as a user may come back to their link. An assessment's
age is that of its newest checkpoint, so one being answered today is never deleted. The
deletion goes through LangGraph's own delete_thread (checkpoints, blobs and writes).
Run daily (a systemd timer on the server, a CronJob on Kubernetes):

    uv run --env-file .env python -m backend.app.retention [--days 30] [--dry-run]
"""

import argparse
import os
from datetime import datetime, timedelta

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

from backend.app.agent.graph import SERDE
from backend.app.quota import now


def stale_threads(conn: psycopg.Connection, cutoff: datetime) -> list[str]:
    rows = conn.execute(
        "SELECT thread_id FROM checkpoints GROUP BY thread_id "
        "HAVING max((checkpoint->>'ts')::timestamptz) < %s ORDER BY thread_id",
        (cutoff,),
    ).fetchall()
    return [row["thread_id"] for row in rows]


def purge(conn: psycopg.Connection, cutoff: datetime) -> list[str]:
    """Delete every assessment last touched before the cutoff; return their ids."""
    saver = PostgresSaver(conn, serde=SERDE)
    stale = stale_threads(conn, cutoff)
    for thread_id in stale:
        saver.delete_thread(thread_id)
    return stale


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=int(os.environ.get("RETENTION_DAYS") or 30))
    parser.add_argument("--dry-run", action="store_true", help="count, delete nothing")
    args = parser.parse_args()
    cutoff = now() - timedelta(days=args.days)
    # The checkpointer needs autocommit and dict rows, like the API's pool.
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row) as conn:
        if args.dry_run:
            print(f"{len(stale_threads(conn, cutoff))} assessments older than {args.days} days")
        else:
            print(f"deleted {len(purge(conn, cutoff))} assessments older than {args.days} days")


if __name__ == "__main__":
    main()
