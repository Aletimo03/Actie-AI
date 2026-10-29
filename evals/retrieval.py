"""Score retrieval methods on evals/retrieval_cases.toml.

A result matches an expected id if it is that chunk or inside it: point
art5_p1_c_ii answers a question about art5_p1_c. Broader results do not match:
the whole of art5_p1 does not answer a question about point (f).

recall@k: share of cases with at least one expected chunk in the top k.
MRR: mean of 1 / rank of the first expected chunk (0 when none is in the top 20).
recall@20 is what a re-ranker can work with: it only reorders the candidates it gets.

    uv run --env-file .env python -m evals.retrieval
"""

import os
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import psycopg
from pgvector.psycopg import register_vector

from backend.app.retrieval.hybrid import hybrid_search, search
from backend.app.retrieval.keyword import keyword_search
from backend.app.retrieval.rerank import Reranker
from backend.app.retrieval.scope import Scope
from backend.app.retrieval.vector import vector_search
from ingestion.embed import OllamaEmbedder

CASES = Path(__file__).with_name("retrieval_cases.toml")
DEPTH = 20  # results fetched per query; recall@5, @10, @20 and MRR are computed on these

Search = Callable[[str, str, int], list[str]]  # (query, lang, k) -> chunk ids, best first


@dataclass
class Case:
    query: str
    lang: str
    expected: list[str]
    note: str = ""


@dataclass
class Score:
    method: str
    recall: dict[int, float]
    mrr: float
    misses: list[tuple[Case, list[str]]] = field(default_factory=list)  # not in the top 5


def load_cases(path: Path = CASES) -> list[Case]:
    return [Case(**c) for c in tomllib.loads(path.read_text(encoding="utf-8"))["case"]]


def matches(result: str, expected: str) -> bool:
    return result == expected or result.startswith(f"{expected}_")


def first_rank(expected: list[str], results: list[str]) -> int | None:
    """1-based rank of the first result matching an expected id, or None."""
    return next((i for i, r in enumerate(results, 1) if any(matches(r, e) for e in expected)), None)


def score(
    method: str, search: Search, cases: list[Case], ks: tuple[int, ...] = (5, 10, 20)
) -> Score:
    ranks, misses = [], []
    for case in cases:
        results = search(case.query, case.lang, DEPTH)
        rank = first_rank(case.expected, results)
        ranks.append(rank)
        if rank is None or rank > 5:
            misses.append((case, results[:3]))
    recall = {k: sum(r is not None and r <= k for r in ranks) / len(cases) for k in ks}
    mrr = sum(1 / r for r in ranks if r) / len(cases)
    return Score(method, recall, mrr, misses)


def report(scores: list[Score]) -> str:
    lines = [f"{'method':<22}{'recall@5':>10}{'recall@10':>11}{'recall@20':>11}{'MRR':>7}"]
    lines += [
        f"{s.method:<22}{s.recall[5]:>10.2f}{s.recall[10]:>11.2f}{s.recall[20]:>11.2f}{s.mrr:>7.2f}"
        for s in scores
    ]
    for s in scores:
        lines.append(f"\n{s.method}: {len(s.misses)} cases without an expected chunk in the top 5")
        for case, top in s.misses:
            lines.append(f"  [{case.lang}] {case.query}\n      want {case.expected}, got {top}")
    return "\n".join(lines)


def ids(hits) -> list[str]:
    return [h.id for h in hits]


def main() -> None:
    cases = load_cases()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, httpx.Client(timeout=60) as client:
        register_vector(conn)
        embedder = OllamaEmbedder(client)
        reranker = Reranker()
        methods: dict[str, Search] = {
            "vector": lambda q, lang, k: ids(vector_search(conn, embedder, q, Scope(lang), k)),
            "keyword (BM25)": lambda q, lang, k: ids(keyword_search(conn, q, Scope(lang), k)),
            "hybrid (RRF)": lambda q, lang, k: ids(
                hybrid_search(conn, embedder, q, Scope(lang), k)
            ),
            "hybrid, binding only": lambda q, lang, k: ids(
                hybrid_search(conn, embedder, q, Scope(lang, binding_only=True), k)
            ),
            "hybrid + rerank": lambda q, lang, k: ids(
                search(conn, embedder, reranker, q, Scope(lang, binding_only=True), k)
            ),
        }
        print(f"{len(cases)} cases\n")
        print(report([score(name, search, cases) for name, search in methods.items()]))


if __name__ == "__main__":
    main()
