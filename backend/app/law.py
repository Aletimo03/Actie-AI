"""The law as the agent reads it: provisions fetched by id from the current version.

Each legal step knows exactly which provisions it must judge (all of Article 5(1), all of
Annex III), so it loads them directly: a top-k search could only lose one. The search code
built for the law (evals/search/) is measured by the retrieval eval and not used here.
"""

from dataclasses import dataclass

import psycopg

CURRENT_VERSION = "(SELECT version FROM versions WHERE is_current)"  # a SQL subquery


@dataclass
class Context:
    id: str
    header: str
    text: str


def fetch_contexts(conn: psycopg.Connection, ids: list[str]) -> list[Context]:
    """The contexts with these ids, in the order asked; missing ids raise."""
    rows = conn.execute(
        f"SELECT id, header, text FROM contexts WHERE version = {CURRENT_VERSION} "
        "AND id = ANY(%(ids)s)",
        {"ids": ids},
    ).fetchall()
    found = {row[0]: Context(*row) for row in rows}
    if missing := [i for i in ids if i not in found]:
        raise LookupError(f"contexts not in the current version: {missing}")
    return [found[i] for i in ids]
