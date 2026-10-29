"""Shared fixtures. `db` gives a connection inside a throwaway schema of the compose database."""

import os
import uuid

import pytest

from ingestion.embed import content_hash

MODEL = "test-model"


@pytest.fixture
def db():
    psycopg = pytest.importorskip("psycopg")
    from pgvector.psycopg import register_vector

    from ingestion.load import SCHEMA

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("needs DATABASE_URL (uv run --env-file .env pytest)")
    try:
        connection = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("database not running (docker compose up -d)")
    schema = f"test_{uuid.uuid4().hex[:8]}"
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


def make_rows(texts: dict[str, str], lang: str = "en"):
    """Chunks, contexts and vectors for load(), one chunk per id -> text."""
    contexts = [
        {"id": i, "lang": lang, "header": "h", "text": t, "source": "s"} for i, t in texts.items()
    ]
    chunks = [
        {
            "id": i, "lang": lang, "kind": "point", "header": "AI Act › Article 1", "text": t,
            "embed_text": f"AI Act › Article 1\n{t}", "context_id": i, "article": "1",
            "paragraph": "", "annex": "", "chapter": "I", "refs": [], "binding": True,
            "amended": False, "source": "s",
        }
        for i, t in texts.items()
    ]  # fmt: skip
    vectors = {content_hash(MODEL, c["embed_text"]): [1.0] + [0.0] * 1023 for c in chunks}
    return chunks, contexts, vectors
