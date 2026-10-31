import gzip
import json
import os

import pytest

from backend.app.agent.citations import fetch_chunks
from backend.app.retrieval.contexts import fetch_contexts
from evals.law_snapshot import SNAPSHOT, export, load


def snapshot_version() -> str:
    first = gzip.decompress(SNAPSHOT.read_bytes()).split(b"\n", 1)[0]
    row = json.loads(first)
    assert row["table"] == "versions"
    return row["version"]


def test_the_agent_reads_the_law_from_a_loaded_snapshot(db):
    counts = load(db)
    assert counts["versions"] == 1 and counts["contexts"] > 2000 and counts["chunks"] > 3000

    [context] = fetch_contexts(db, ["en_art5_p1"])
    assert "prohibited" in context.text  # Art. 5(1): the prohibited practices
    chunks = fetch_chunks(db, ["en_annex3_4_a"])
    assert any(c.id == "en_annex3_4_a" and "recruitment" in c.text for c in chunks)
    # No real vectors: marked, so nothing mistakes them for embeddings.
    models = db.execute("SELECT DISTINCT embedding_model FROM chunks").fetchall()
    assert models == [("none (snapshot)",)]


def test_export_then_load_gives_the_same_rows(db, tmp_path):
    load(db)
    copy = tmp_path / "again.jsonl.gz"
    export(db, copy)
    assert copy.read_bytes() == SNAPSHOT.read_bytes()  # deterministic: no spurious git diffs


def test_the_snapshot_is_the_law_in_the_local_database():
    """Fails after a new version of the law is loaded until the snapshot is exported."""
    psycopg = pytest.importorskip("psycopg")
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("needs DATABASE_URL (uv run --env-file .env pytest)")
    try:
        conn = psycopg.connect(url)
    except psycopg.OperationalError:
        pytest.skip("database not running (docker compose up -d)")
    with conn:
        current = conn.execute("SELECT version FROM versions WHERE is_current").fetchone()
    if current is None:
        pytest.skip("no law loaded in this database (CI)")
    assert snapshot_version() == current[0], "run: python -m evals.law_snapshot export"
