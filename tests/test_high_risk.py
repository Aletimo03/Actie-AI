from backend.app.agent.facts import Facts
from backend.app.agent.high_risk import (
    ANNEX_I,
    ANNEX_III,
    ARTICLE_6,
    HighRiskCheck,
    check_high_risk,
    decide,
    point_id,
)
from backend.app.retrieval.contexts import Context

NO = {"applies": "no", "reason": "No."}
MATCH = {"applies": "yes", "point": "4(a)", "reason": "Ranks CVs.", "quote": "recruitment"}
NARROW = {"applies": "yes", "condition": "a", "reason": "Only reformats.", "quote": "narrow"}


def check(annex_i=NO, annex_iii=NO, exception=NO) -> HighRiskCheck:
    return HighRiskCheck(annex_i=annex_i, annex_iii=annex_iii, exception=exception)


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def ask(self, system, user, schema):
        self.calls.append((system, user, schema))
        return self.reply


def test_point_id_reads_the_annex_iii_point():
    assert point_id("4(a)", "en") == "en_annex3_4_a"
    assert point_id("5 (b)", "it") == "it_annex3_5_b"
    assert point_id("4", "en") == "en_annex3_4"
    assert point_id(None, "en") == point_id("Annex III", "en") == "en_annex3"


def test_nothing_matches_is_not_high_risk():
    result = decide(check(), Facts(), "en")
    assert not result.is_high_risk and result.citations == [] and result.questions == []


def test_annex_i_product_is_high_risk_under_article_6_1():
    product = {"applies": "yes", "reason": "Medical device.", "quote": "safety component"}
    result = decide(check(annex_i=product), Facts(), "en")
    assert result.is_high_risk and result.basis == ["en_art6_p1"]


def test_annex_iii_match_is_high_risk_and_cites_the_point():
    result = decide(check(annex_iii=MATCH), Facts(profiles_people=True), "it")
    assert result.basis == ["it_annex3_4_a"]
    assert (result.citations[0].chunk_id, result.citations[0].quote) == (
        "it_annex3_4_a",
        "recruitment",
    )


def test_exception_applies_only_without_profiling():
    excepted = decide(check(annex_iii=MATCH, exception=NARROW), Facts(profiles_people=False), "en")
    assert not excepted.is_high_risk and excepted.exception == "a"
    assert excepted.citations[0].chunk_id == "en_art6_p3"

    profiled = decide(check(annex_iii=MATCH, exception=NARROW), Facts(profiles_people=True), "en")
    assert profiled.is_high_risk and profiled.exception is None and profiled.questions == []


def test_unknown_profiling_is_asked_and_counts_as_high_risk():
    result = decide(check(annex_iii=MATCH, exception=NARROW), Facts(), "it")
    assert result.is_high_risk and result.uncertain == ["profiling"]
    assert result.questions[0].startswith("Il sistema valuta")


def test_uncertain_findings_become_questions():
    unsure = {"applies": "uncertain", "reason": "?", "question": "Is it used in hiring?"}
    annex = decide(check(annex_iii=unsure), Facts(), "en")
    assert not annex.is_high_risk and annex.questions == ["Is it used in hiring?"]

    open_exception = {"applies": "uncertain", "reason": "?", "question": "Does a human review it?"}
    result = decide(check(annex_iii=MATCH, exception=open_exception), Facts(), "en")
    assert result.is_high_risk and result.questions == ["Does a human review it?"]


def test_annex_i_text_is_loaded_only_for_products():
    asked = []

    def fetch(ids):
        asked.append(ids)
        return [Context(i, i, "text") for i in ids]

    llm = FakeLLM(check())
    check_high_risk(llm, fetch, "A CV ranker.", Facts(domain="employment"), "en")
    check_high_risk(llm, fetch, "An insulin pump.", Facts(domain="product_safety"), "it")
    assert asked[0] == [f"en_{u}" for u in ARTICLE_6 + ANNEX_III]
    assert asked[1] == [f"it_{u}" for u in ARTICLE_6 + ANNEX_III + ANNEX_I]
    assert "Write reasons and questions in Italian." in llm.calls[1][0]
