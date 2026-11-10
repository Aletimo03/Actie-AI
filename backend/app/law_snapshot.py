"""The law the agent reads, as a small file: to fill an empty database without ingestion.

Used by the agent eval in CI and by the jobs that load the law on the server and on Kubernetes.

The agent never searches by vector: it reads contexts and chunks by id. So the snapshot
holds the current version's rows without their embeddings (0.9 MB instead of ~40 MB, and
no Ollama needed to rebuild them). `load` writes them into the real schema with zero
vectors marked `embedding_model = 'none (snapshot)'`, so the agent's own SQL runs against
the same tables as in production. Vector search on such a database finds nothing useful:
it is for the agent and its eval, not the retrieval eval.

Export again after loading a new version of the law (a test fails while they differ):

    uv run --env-file .env python -m backend.app.law_snapshot export
    DATABASE_URL=... uv run python -m backend.app.law_snapshot load
"""

import argparse
import gzip
import json
import os
from pathlib import Path

import psycopg

from backend.app.law import CURRENT_VERSION

DB = Path(__file__).parents[2] / "db"
SNAPSHOT = DB / "law_snapshot.jsonl.gz"
SCHEMA = DB / "schema.sql"
COLUMNS = {
    "versions": ["version"],
    "contexts": ["id", "version", "lang", "header", "text", "source"],
    "chunks": [
        "id", "version", "lang", "kind", "header", "text", "embed_text", "context_id",
        "article", "paragraph", "annex", "chapter", "refs", "binding", "amended", "source",
        "content_hash",
    ],
}  # fmt: skip
DIMENSIONS = 1024  # chunks.embedding is vector(1024)


def export(conn: psycopg.Connection, path: Path = SNAPSHOT) -> dict[str, int]:
    counts, lines = {}, []
    for table, columns in COLUMNS.items():
        where = "is_current" if table == "versions" else f"version = {CURRENT_VERSION}"
        rows = conn.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE {where} ORDER BY 1"
        ).fetchall()
        counts[table] = len(rows)
        lines += [json.dumps({"table": table, **dict(zip(columns, row, strict=True))},
                             ensure_ascii=False) for row in rows]  # fmt: skip
    # mtime=0 and sorted rows: the same law gives the same content, so an export on the same
    # machine leaves git with no change (other zlib builds may compress it differently).
    path.write_bytes(gzip.compress("\n".join(lines).encode() + b"\n", mtime=0))
    return counts


def load(conn: psycopg.Connection, path: Path = SNAPSHOT) -> dict[str, int]:
    by_table: dict[str, list[dict]] = {table: [] for table in COLUMNS}
    for line in gzip.decompress(path.read_bytes()).splitlines():
        row = json.loads(line)
        by_table[row.pop("table")].append(row)
    # Filled in on load: the snapshot's version is current, and no real vectors exist.
    extra = {
        "versions": (["is_current"], [True]),
        "contexts": ([], []),
        "chunks": (["embedding", "embedding_model"], ["[" + ",".join(["0"] * DIMENSIONS) + "]",
                                                      "none (snapshot)"]),
    }  # fmt: skip
    [version] = [row["version"] for row in by_table["versions"]]
    with conn.transaction():
        conn.execute(SCHEMA.read_text())
        # Runs on every deploy (a Kubernetes Job): a version already there, from an earlier
        # run or from real ingestion with real embeddings, is left as it is.
        if conn.execute("SELECT 1 FROM versions WHERE version = %s", (version,)).fetchone():
            return dict.fromkeys(COLUMNS, 0)
        # A newer law replaces the current one: the index allows one current version.
        conn.execute("UPDATE versions SET is_current = false WHERE is_current")
        for table, columns in COLUMNS.items():
            names, values = extra[table]
            sql = f"COPY {table} ({', '.join(columns + names)}) FROM STDIN"
            with conn.cursor().copy(sql) as copy:
                for row in by_table[table]:
                    copy.write_row([row[c] for c in columns] + values)
    return {table: len(rows) for table, rows in by_table.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["export", "load"])
    args = parser.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        counts = (export if args.command == "export" else load)(conn)
    print(f"{args.command}: " + ", ".join(f"{n} {table}" for table, n in counts.items()))


if __name__ == "__main__":
    main()
