"""Load stage: chunks, contexts and vectors -> Postgres, in one transaction.

The schema is applied first (it is idempotent). Then, inside a single
transaction: the version row is upserted, contexts and chunks are upserted,
rows of this version that no longer exist are deleted, and this version
becomes the only current one. Any error rolls everything back, so the
database always holds the previous complete load or the new complete load.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from ingestion.chunk import latest_processed, read_jsonl
from ingestion.embed import EMBEDDING_MODEL, content_hash, read_cache

SCHEMA = Path("db/schema.sql")
LANGS = ("en", "it")

CHUNK_COLUMNS = [
    "id", "version", "lang", "kind", "header", "text", "embed_text", "context_id", "article",
    "paragraph", "annex", "chapter", "refs", "binding", "amended", "source", "content_hash",
    "embedding", "embedding_model",
]  # fmt: skip
CONTEXT_COLUMNS = ["id", "version", "lang", "header", "text", "source"]


def upsert_sql(table: str, columns: list[str]) -> str:
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in ("id", "version"))
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) "
        f"ON CONFLICT (id, version) DO UPDATE SET {updates}"
    )


@dataclass
class LoadResult:
    version: str
    contexts: int
    chunks: int
    deleted: int


def chunk_rows(chunks: list[dict], vectors: dict[str, list[float]], version: str, model: str):
    for chunk in chunks:
        digest = content_hash(model, chunk["embed_text"])
        if digest not in vectors:
            raise SystemExit(f"no vector for {chunk['id']}: run `python -m ingestion.embed` first")
        row = {**chunk, "version": version, "content_hash": digest, "embedding_model": model}
        row["embedding"] = Vector(vectors[digest])
        yield tuple(row[c] for c in CHUNK_COLUMNS)


def load(
    conn: psycopg.Connection,
    version: str,
    chunks: list[dict],
    contexts: list[dict],
    vectors: dict[str, list[float]],
    model: str = EMBEDDING_MODEL,
) -> LoadResult:
    """Replace this version's rows with the given ones and make it current, atomically."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "INSERT INTO versions (version) VALUES (%s) ON CONFLICT (version) DO NOTHING",
            (version,),
        )
        cur.executemany(
            upsert_sql("contexts", CONTEXT_COLUMNS),
            [tuple({**c, "version": version}[k] for k in CONTEXT_COLUMNS) for c in contexts],
        )
        cur.executemany(
            upsert_sql("chunks", CHUNK_COLUMNS), list(chunk_rows(chunks, vectors, version, model))
        )
        # Rows a re-parse no longer produces (deleting contexts cascades to their chunks).
        cur.execute(
            "DELETE FROM chunks WHERE version = %s AND NOT (id = ANY(%s))",
            (version, [c["id"] for c in chunks]),
        )
        deleted = cur.rowcount
        cur.execute(
            "DELETE FROM contexts WHERE version = %s AND NOT (id = ANY(%s))",
            (version, [c["id"] for c in contexts]),
        )
        deleted += cur.rowcount
        # Two statements: the unique index allows only one current row at any moment.
        cur.execute(
            "UPDATE versions SET is_current = false WHERE is_current AND version <> %s", (version,)
        )
        cur.execute(
            "UPDATE versions SET is_current = true, loaded_at = now() WHERE version = %s",
            (version,),
        )
    return LoadResult(version, len(contexts), len(chunks), deleted)


def connect(url: str) -> psycopg.Connection:
    conn = psycopg.connect(url)
    with conn.transaction():
        conn.execute(SCHEMA.read_text(encoding="utf-8"))  # creates the vector extension first
    register_vector(conn)
    return conn


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set: run with `uv run --env-file .env ...`")
    folder = latest_processed()
    chunks, contexts, vectors = [], [], {}
    for lang in LANGS:
        chunks += read_jsonl(folder / f"chunks_{lang}.jsonl")
        contexts += read_jsonl(folder / f"contexts_{lang}.jsonl")
        vectors |= read_cache(folder / f"embeddings_{lang}.jsonl")
    with connect(url) as conn:
        result = load(conn, folder.name, chunks, contexts, vectors)
    print(
        f"{result.version}: {result.contexts} contexts and {result.chunks} chunks loaded, "
        f"{result.deleted} stale rows deleted; now the current version"
    )


if __name__ == "__main__":
    main()
