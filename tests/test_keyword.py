from conftest import MODEL, make_rows

from backend.app.retrieval.keyword import keyword_search
from backend.app.retrieval.scope import Scope
from ingestion.load import load

TEXTS = {
    "en_common": "AI systems and AI models: the AI system shall comply with this Act.",
    "en_rare": "AI systems that infer the emotions of a natural person in the workplace.",
    "en_other": "Providers of general-purpose AI models shall keep documentation.",
}


def test_rare_words_outrank_words_found_everywhere(db):
    load(db, "v1", *make_rows(TEXTS), MODEL)
    hits = keyword_search(db, "Can an AI system detect emotions of employees?", Scope("en"))
    assert hits[0].id == "en_rare"  # 'emot' is rare; 'ai' and 'system' are in every chunk


def test_words_are_stemmed(db):
    load(db, "v1", *make_rows(TEXTS), MODEL)
    assert keyword_search(db, "emotional", Scope("en"))[0].id == "en_rare"


def test_italian_uses_italian_stemming(db):
    texts = {
        "it_a": "sistemi che deducono le emozioni di una persona fisica",
        "it_b": "modelli di IA",
    }
    load(db, "v1", *make_rows(texts, lang="it"), MODEL)
    assert [h.id for h in keyword_search(db, "emozione", Scope("it"))] == ["it_a"]


def test_no_match_returns_nothing(db):
    load(db, "v1", *make_rows(TEXTS), MODEL)
    assert keyword_search(db, "xylophone", Scope("en")) == []
