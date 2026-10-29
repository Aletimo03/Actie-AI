from conftest import MODEL, make_rows

from backend.app.retrieval.hybrid import rrf
from backend.app.retrieval.keyword import keyword_search
from backend.app.retrieval.scope import Scope
from backend.app.retrieval.vector import Hit
from ingestion.load import load


def hits(*ids):
    return [Hit(i, 0.0, "h", "t", i) for i in ids]


def test_rrf_prefers_chunks_ranked_well_by_both_lists():
    # x: ranks 1 and 10 -> 1/61 + 1/70 = 0.0307; y: ranks 3 and 3 -> 2/63 = 0.0317 (Lecture 04)
    vector = hits("x", "a", "y", *[f"v{n}" for n in range(7)])
    keyword = hits("b", "c", "y", *[f"k{n}" for n in range(6)], "x")
    fused = rrf([vector, keyword])
    assert [h.id for h in fused[:2]] == ["y", "x"]
    assert fused[0].score == 2 / 63


def test_rrf_keeps_chunks_found_by_one_list_only():
    assert [h.id for h in rrf([hits("a"), hits("b")])] == ["a", "b"]  # equal score: by id


def test_scope_limits_results_to_articles_annexes_and_binding_text(db):
    chunks, contexts, vectors = make_rows(
        {
            "en_art5_p1_f": "emotions at work",
            "en_rec18": "emotions explained",
            "en_annex3_1_c": "emotions",
        }
    )
    chunks[0]["article"], chunks[2]["article"], chunks[2]["annex"] = "5", "", "III"
    chunks[1].update(article="", kind="recital", binding=False)
    load(db, "v1", chunks, contexts, vectors, MODEL)

    def found(scope):
        return sorted(h.id for h in keyword_search(db, "emotions", scope))

    assert found(Scope("en")) == ["en_annex3_1_c", "en_art5_p1_f", "en_rec18"]
    assert found(Scope("en", binding_only=True)) == ["en_annex3_1_c", "en_art5_p1_f"]
    assert found(Scope("en", articles=["5"])) == ["en_art5_p1_f"]
    assert found(Scope("en", articles=["5"], annexes=["III"])) == ["en_annex3_1_c", "en_art5_p1_f"]
