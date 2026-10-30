from conftest import MODEL, make_rows

from backend.app.agent.citations import Chunk, fetch_chunks, normalise, quote_in, verify
from backend.app.agent.prohibited import Citation
from ingestion.load import load

POINT_F = (
    "the placing on the market, the putting into service for this specific purpose, or the use "
    "of AI systems to infer emotions of a natural person in the areas of workplace and education "
    "institutions, except where the use of the AI system is intended to be put in place or into "
    "the market for medical or safety reasons;"
)
LAW = [
    Chunk("en_art6_p3", "en_art6_p3", "By derogation from paragraph 2, an AI system referred to "
          "in Annex III shall not be considered to be high-risk"),
    Chunk("en_art6_p3_a", "en_art6_p3", "the AI system is intended to perform a narrow "
          "procedural task;"),
    Chunk("en_art5_p1_f", "en_art5_p1", POINT_F),
]  # fmt: skip


def lookup(ids):
    contexts = {c.context_id for c in LAW if c.id in ids}
    return [c for c in LAW if c.context_id in contexts]


def cite(chunk_id, quote):
    return Citation(chunk_id=chunk_id, quote=quote, claim="A claim.")


def test_normalise_ignores_layout_typography_and_case():
    assert normalise(" The “Person’s\n  data” – ok. ") == 'the "person\'s data" - ok'


def test_a_long_quote_copied_with_other_line_breaks_matches():
    quote = "to infer emotions of a natural person\nin the areas of Workplace and education"
    assert quote_in(quote, POINT_F)


def test_an_ellipsis_skips_words_but_the_fragments_must_keep_their_order():
    assert quote_in(
        "the use of AI systems to infer emotions ... medical or safety reasons", POINT_F
    )
    assert quote_in("infer emotions […] workplace", POINT_F)
    assert not quote_in("workplace ... infer emotions", POINT_F)


def test_one_changed_word_fails():
    assert not quote_in("shall be considered to be high-risk", LAW[0].text)
    assert not quote_in("...", POINT_F)


def test_each_citation_is_checked_against_its_chunk():
    good, invented, empty, unknown = verify(
        [
            cite("en_art5_p1_f", "infer emotions of a natural person"),
            cite("en_art5_p1_f", "emotions of employees during video calls"),
            cite("en_art5_p1_f", " "),
            cite("en_annex3_9_z", "anything"),
        ],
        lookup,
    )
    assert (good.verified, good.note) == (True, "")
    assert (invented.verified, invented.note) == (False, "quote not found in en_art5_p1_f")
    assert (empty.verified, empty.note) == (False, "no quote given")
    assert (unknown.verified, unknown.note) == (False, "not a provision of the current text")


def test_a_quote_from_a_sibling_point_moves_the_citation_there():
    [moved] = verify([cite("en_art6_p3", "a narrow procedural task")], lookup)
    assert (moved.chunk_id, moved.verified) == ("en_art6_p3_a", True)
    assert moved.note == "quote found in en_art6_p3_a, not en_art6_p3"
    assert moved.claim == "A claim."


def test_no_citations_need_no_lookup():
    def fail(ids):
        raise AssertionError("no lookup expected")

    assert verify([], fail) == []


def test_fetch_chunks_returns_the_siblings_and_skips_unknown_ids(db):
    chunks, contexts, vectors = make_rows(
        {"en_art6_p3": "lead-in", "en_art6_p3_a": "point a", "en_art5_p1": "other"}
    )
    chunks[1]["context_id"] = "en_art6_p3"
    load(db, "v1", chunks, contexts, vectors, MODEL)
    found = fetch_chunks(db, ["en_art6_p3", "en_annex3_9_z"])
    assert [(c.id, c.context_id, c.text) for c in found] == [
        ("en_art6_p3", "en_art6_p3", "lead-in"),
        ("en_art6_p3_a", "en_art6_p3", "point a"),
    ]
