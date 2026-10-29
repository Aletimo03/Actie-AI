"""Semantic search: the chunks whose bge-m3 vectors are closest to the question's."""

from dataclasses import dataclass

import psycopg
from pgvector import Vector

from backend.app.retrieval.scope import Scope
from ingestion.embed import OllamaEmbedder


@dataclass
class Hit:
    id: str
    score: float  # method-specific: cosine similarity, BM25 score or RRF score
    header: str
    text: str
    context_id: str


def vector_search(
    conn: psycopg.Connection, embedder: OllamaEmbedder, query: str, scope: Scope, k: int = 10
) -> list[Hit]:
    where, params = scope.where()
    rows = conn.execute(
        f"""
        SELECT id, 1 - (embedding <=> %(v)s), header, text, context_id
        FROM chunks
        WHERE {where}
        ORDER BY embedding <=> %(v)s
        LIMIT %(k)s
        """,
        params | {"v": Vector(embedder.embed([query])[0]), "k": k},
    ).fetchall()
    return [Hit(*row) for row in rows]
