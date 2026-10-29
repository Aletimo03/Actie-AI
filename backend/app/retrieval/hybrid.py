"""Hybrid search: vector and keyword results merged with reciprocal rank fusion.

    rrf(chunk) = sum over the two result lists of 1 / (K + rank of the chunk in that list)

RRF uses ranks only, so the cosine similarities and BM25 scores, which are on
unrelated scales, never need to be compared. A chunk ranked well by both
searches beats one ranked first by only one of them (Lecture 04).
"""

import psycopg

from backend.app.retrieval.keyword import keyword_search
from backend.app.retrieval.scope import Scope
from backend.app.retrieval.vector import Hit, vector_search
from ingestion.embed import OllamaEmbedder

K = 60  # the constant from the original RRF paper; larger values flatten the rank differences
DEPTH = 20  # results taken from each search before fusing


def rrf(result_lists: list[list[Hit]], k: int = K) -> list[Hit]:
    """Fuse ranked lists; each hit's score becomes its RRF score."""
    scores: dict[str, float] = {}
    first_seen: dict[str, Hit] = {}
    for hits in result_lists:
        for rank, hit in enumerate(hits, 1):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1 / (k + rank)
            first_seen.setdefault(hit.id, hit)
    ranked = sorted(scores, key=lambda i: (-scores[i], i))
    return [
        Hit(i, scores[i], first_seen[i].header, first_seen[i].text, first_seen[i].context_id)
        for i in ranked
    ]


def hybrid_search(
    conn: psycopg.Connection,
    embedder: OllamaEmbedder,
    query: str,
    scope: Scope,
    k: int = 10,
    depth: int = DEPTH,
) -> list[Hit]:
    vector_hits = vector_search(conn, embedder, query, scope, depth)
    keyword_hits = keyword_search(conn, query, scope, depth)
    return rrf([vector_hits, keyword_hits])[:k]
