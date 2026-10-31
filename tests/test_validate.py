import copy
from pathlib import Path

import pytest

from ingestion import validate as v


def good_data() -> v.Data:
    """The smallest dataset that passes every check (with the patched expectations below)."""

    def rows(lang, rule):
        nodes = [
            {"id": f"{lang}_art1", "kind": "article"},
            {"id": f"{lang}_annex1", "kind": "annex"},
            {"id": f"{lang}_rec1", "kind": "recital"},
        ]
        chunk = {
            "id": f"{lang}_art1_p1",
            "text": rule,
            "embed_text": f"AI Act › Article 1 › 1\n{rule}",
            "context_id": f"{lang}_art1_p1",
            "refs": ["annex1"],
            "amended": False,
        }
        context = {"id": f"{lang}_art1_p1", "text": f"1 {rule}"}
        return nodes, [chunk], [context]

    en, it = rows("en", "A rule referred to in Annex I."), rows("it", "Una regola dell'allegato I.")
    return v.Data(
        nodes={"en": en[0], "it": it[0]},
        chunks={"en": en[1], "it": it[1]},
        contexts={"en": en[2], "it": it[2]},
    )


@pytest.fixture(autouse=True)
def small_expectations(monkeypatch):
    monkeypatch.setattr(v, "EXPECTED_COUNTS", {"article": 1, "annex": 1, "recital": 1})
    monkeypatch.setattr(v, "SPOT_CHECKS", {"art1_p1": {"en": "rule", "it": "regola"}})


def failing(data: v.Data) -> list[str]:
    return [c.name.split(":")[0] for c in v.validate(data) if not c.ok]


def test_good_data_passes_every_check():
    assert failing(good_data()) == []


def broken(change) -> list[str]:
    data = copy.deepcopy(good_data())
    change(data)
    return failing(data)


def test_missing_article_fails_counts():
    assert broken(lambda d: d.nodes["it"].pop(0)) == ["counts"]


def test_missing_italian_twin_fails_twins():
    assert "twins" in broken(lambda d: d.chunks["it"].clear())


def test_amended_flag_must_match_between_languages():
    assert broken(lambda d: d.chunks["it"][0].update(amended=True)) == ["twins"]


def test_duplicate_and_dangling_ids_fail_ids():
    assert broken(lambda d: d.chunks["en"].append(d.chunks["en"][0])) == ["ids"]
    assert broken(lambda d: d.chunks["en"][0].update(context_id="en_nowhere")) == ["ids"]


def test_empty_or_huge_chunks_fail_sizes():
    assert "sizes" in broken(lambda d: d.chunks["en"][0].update(text=" "))
    assert broken(lambda d: d.chunks["en"][0].update(embed_text="word " * 2000)) == ["sizes"]


def test_unknown_reference_fails_refs():
    assert broken(lambda d: d.chunks["en"][0].update(refs=["art999"])) == ["refs"]


def test_leftover_markup_fails_text():
    assert broken(lambda d: d.contexts["en"][0].update(text="▼M1 1 A rule")) == ["text"]


def test_a_word_glued_in_the_official_text_fails_text():
    def glue(data):
        data.contexts["it"][0]["text"] += " sistemi di IAper la valutazione"

    assert broken(glue) == ["text"]


def test_wrong_wording_fails_spot_checks():
    assert broken(lambda d: d.chunks["it"][0].update(text="Altro testo.")) == ["spot checks"]


RAW = Path("data/processed")


@pytest.mark.skipif(
    not any(RAW.glob("02024R1689-*/chunks_en.jsonl")), reason="run the pipeline first"
)
def test_real_data_passes_the_gate(monkeypatch):
    monkeypatch.undo()  # the real expectations: 119 articles, real spot checks
    results = v.validate(v.load(v.latest_processed()))
    assert [c.name for c in results if not c.ok] == []
