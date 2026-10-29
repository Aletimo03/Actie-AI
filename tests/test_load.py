"""Runs against the compose database, inside a throwaway schema; skipped without DATABASE_URL."""

import os
import uuid

import pytest

from ingestion.embed import content_hash
from ingestion.load import SCHEMA, load

psycopg = pytest.importorskip("psycopg")
from pgvector.psycopg import register_vector  # noqa: E402

URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="needs DATABASE_URL (uv run --env-file .env pytest)"
)
MODEL = "test-model"


@pytest.fixture
def conn():
    schema = f"test_{uuid.uuid4().hex[:8]}"
    try:
        connection = psycopg.connect(URL, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("database not running (docker compose up -d)")
    connection.execute(f"CREATE SCHEMA {schema}")
    connection.execute(f"SET search_path TO {schema}, public")
    connection.execute(SCHEMA.read_text(encoding="utf-8"))
    register_vector(connection)
    connection.autocommit = False
    yield connection
    connection.rollback()
    connection.autocommit = True
    connection.execute(f"DROP SCHEMA {schema} CASCADE")
    connection.close()


def data(*ids):
    contexts = [
        {"id": i, "lang": "en", "header": "h", "text": f"text {i}", "source": "s"} for i in ids
    ]
    chunks = [
        {
            "id": i, "lang": "en", "kind": "point", "header": "h", "text": f"text {i}",
            "embed_text": f"h\ntext {i}", "context_id": i, "article": "6", "paragraph": "3",
            "annex": "", "chapter": "III", "refs": ["annex3"], "binding": True, "amended": False,
            "source": "s",
        }
        for i in ids
    ]  # fmt: skip
    vectors = {content_hash(MODEL, c["embed_text"]): [1.0] + [0.0] * 1023 for c in chunks}
    return chunks, contexts, vectors


def count(conn, table, version):
    return conn.execute(f"SELECT count(*) FROM {table} WHERE version = %s", (version,)).fetchone()[
        0
    ]


def current(conn):
    return [r[0] for r in conn.execute("SELECT version FROM versions WHERE is_current")]


def test_load_is_idempotent(conn):
    chunks, contexts, vectors = data("en_a", "en_b")
    load(conn, "v1", chunks, contexts, vectors, MODEL)
    result = load(conn, "v1", chunks, contexts, vectors, MODEL)
    assert (count(conn, "chunks", "v1"), count(conn, "contexts", "v1"), result.deleted) == (2, 2, 0)
    assert current(conn) == ["v1"]


def test_rows_a_reload_no_longer_has_are_deleted(conn):
    load(conn, "v1", *data("en_a", "en_b"), MODEL)
    result = load(conn, "v1", *data("en_a"), MODEL)
    assert (count(conn, "chunks", "v1"), result.deleted) == (1, 2)  # one chunk + its context


def test_new_version_becomes_the_only_current_one(conn):
    load(conn, "v1", *data("en_a"), MODEL)
    load(conn, "v2", *data("en_a"), MODEL)
    assert current(conn) == ["v2"]
    assert count(conn, "chunks", "v1") == 1  # the old version stays, just not current


def test_failure_rolls_everything_back(conn):
    load(conn, "v1", *data("en_a"), MODEL)
    chunks, contexts, _ = data("en_a", "en_b")
    with pytest.raises(SystemExit, match="no vector"):
        load(conn, "v2", chunks, contexts, {}, MODEL)  # vectors missing
    assert current(conn) == ["v1"]
    assert count(conn, "contexts", "v2") == 0


def test_keyword_column_is_generated(conn):
    load(conn, "v1", *data("en_a"), MODEL)
    tsv = conn.execute("SELECT tsv::text FROM chunks WHERE id = 'en_a'").fetchone()[0]
    assert "'text'" in tsv
