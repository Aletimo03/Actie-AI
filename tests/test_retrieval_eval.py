import json
from pathlib import Path

import pytest

from evals.retrieval import Case, first_rank, load_cases, score


def test_first_rank():
    assert first_rank(["b"], ["a", "b", "c"]) == 2
    assert first_rank(["x", "c"], ["a", "b", "c"]) == 3
    assert first_rank(["x"], ["a"]) is None


def test_recall_and_mrr():
    cases = [Case("q1", "en", ["a"]), Case("q2", "en", ["b"]), Case("q3", "en", ["z"])]
    answers = {"q1": ["a", "x"], "q2": ["x"] * 6 + ["b"], "q3": ["x"]}
    result = score("fake", lambda q, lang, k: answers[q], cases)
    assert result.recall == {5: 1 / 3, 10: 2 / 3}  # q1 at rank 1, q2 at rank 7, q3 missing
    assert result.mrr == pytest.approx((1 + 1 / 7) / 3)
    assert [case.query for case, _ in result.misses] == ["q2", "q3"]


def test_cases_file_is_well_formed():
    cases = load_cases()
    assert len(cases) >= 20
    for case in cases:
        assert case.lang in ("en", "it") and case.expected
        assert all(e.startswith(f"{case.lang}_") for e in case.expected)


CHUNKS = sorted(Path("data/processed").glob("02024R1689-*"))


@pytest.mark.skipif(not CHUNKS, reason="run the ingestion pipeline first")
def test_expected_ids_exist():
    ids = set()
    for lang in ("en", "it"):
        lines = (CHUNKS[-1] / f"chunks_{lang}.jsonl").read_text(encoding="utf-8").splitlines()
        ids |= {json.loads(line)["id"] for line in lines}
    assert [e for c in load_cases() for e in c.expected if e not in ids] == []


def test_a_point_inside_the_expected_chunk_matches_but_a_broader_one_does_not():
    assert first_rank(["en_art5_p1_c"], ["en_art5_p1_c_ii"]) == 1
    assert first_rank(["en_annex4"], ["en_annex3_4", "en_annex4_2"]) == 2
    assert first_rank(["en_art5_p1_f"], ["en_art5_p1"]) is None
    assert first_rank(["en_art5_p1"], ["en_art5_p10"]) is None  # prefix, but another paragraph
