"""Runs against the compose database, inside a throwaway schema; skipped without DATABASE_URL."""

import pytest
from conftest import MODEL, make_rows

from ingestion.load import load


def data(*ids):
    return make_rows({i: f"text {i}" for i in ids})


def count(db, table, version):
    return db.execute(f"SELECT count(*) FROM {table} WHERE version = %s", (version,)).fetchone()[0]


def current(db):
    return [r[0] for r in db.execute("SELECT version FROM versions WHERE is_current")]


def test_load_is_idempotent(db):
    chunks, contexts, vectors = data("en_a", "en_b")
    load(db, "v1", chunks, contexts, vectors, MODEL)
    result = load(db, "v1", chunks, contexts, vectors, MODEL)
    assert (count(db, "chunks", "v1"), count(db, "contexts", "v1"), result.deleted) == (2, 2, 0)
    assert current(db) == ["v1"]


def test_rows_a_reload_no_longer_has_are_deleted(db):
    load(db, "v1", *data("en_a", "en_b"), MODEL)
    result = load(db, "v1", *data("en_a"), MODEL)
    assert (count(db, "chunks", "v1"), result.deleted) == (1, 2)  # one chunk + its context


def test_new_version_becomes_the_only_current_one(db):
    load(db, "v1", *data("en_a"), MODEL)
    load(db, "v2", *data("en_a"), MODEL)
    assert current(db) == ["v2"]
    assert count(db, "chunks", "v1") == 1  # the old version stays, just not current


def test_failure_rolls_everything_back(db):
    load(db, "v1", *data("en_a"), MODEL)
    chunks, contexts, _ = data("en_a", "en_b")
    with pytest.raises(SystemExit, match="no vector"):
        load(db, "v2", chunks, contexts, {}, MODEL)  # vectors missing
    assert current(db) == ["v1"]
    assert count(db, "contexts", "v2") == 0


def test_keyword_column_is_generated(db):
    load(db, "v1", *data("en_a"), MODEL)
    tsv = db.execute("SELECT tsv::text FROM chunks WHERE id = 'en_a'").fetchone()[0]
    assert "'text'" in tsv
