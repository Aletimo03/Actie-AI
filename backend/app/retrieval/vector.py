"""Semantic search: the chunks whose bge-m3 vectors are closest to the question's."""

from dataclasses import dataclass

import psycopg
from pgvector import Vector

from ingestion.embed import OllamaEmbedder


@dataclass
class Hit:
    id: str
    score: float  # cosine similarity, 1 = same meaning
    header: str
    text: str
    context_id: str


CURRENT_VERSION = "(SELECT version FROM versions WHERE is_current)"


def vector_search(
    conn: psycopg.Connection, embedder: OllamaEmbedder, query: str, lang: str, k: int = 10
) -> list[Hit]:
    vector = Vector(embedder.embed([query])[0])
    rows = conn.execute(
        f"""
        SELECT id, 1 - (embedding <=> %(v)s), header, text, context_id
        FROM chunks
        WHERE version = {CURRENT_VERSION} AND lang = %(lang)s
        ORDER BY embedding <=> %(v)s
        LIMIT %(k)s
        """,
        {"v": vector, "lang": lang, "k": k},
    ).fetchall()
    return [Hit(*row) for row in rows]
