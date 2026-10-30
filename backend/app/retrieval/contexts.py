"""Fetch context units (what the LLM reads) by id, from the current version.

Search finds chunks; a step that already knows which provisions it needs
(Article 5(1) is short and every point must be checked) loads them directly.
"""

from dataclasses import dataclass

import psycopg

from backend.app.retrieval.scope import CURRENT_VERSION


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
