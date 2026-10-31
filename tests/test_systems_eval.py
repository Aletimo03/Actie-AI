import re
from types import SimpleNamespace

from langgraph.checkpoint.memory import InMemorySaver
from test_graph import CLEAR, HIGH, KNOWN, LOW, NONE, TODAY, ScriptedLLM, fetch, lookup

from backend.app.agent.graph import QUESTIONS, SERDE, build_graph
from backend.app.agent.prohibited import PRACTICES
from backend.app.agent.role import ARTICLE_25
from evals.systems import RISKS, Outcome, System, assess, load_systems, summarise

BASIS = re.compile(r"^(annex3_[1-8](_[a-e])?|art6_p1)$")


def graph(**replies):
    return build_graph(
        ScriptedLLM(**replies), fetch, lookup, InMemorySaver(serde=SERDE), today=lambda: TODAY
    )


def test_the_systems_file_is_well_formed():
    systems = load_systems()
    assert len(systems) >= 50 and len({s.id for s in systems}) == len(systems)
    assert {s.risk for s in systems} == set(RISKS) and {s.lang for s in systems} == {"en", "it"}
    questions = set(QUESTIONS) | {"art25"}
    for s in systems:
        assert s.risk in RISKS and s.why, s.id
        assert all(BASIS.match(b) for b in s.basis), s.id
        assert set(s.banned) <= set(PRACTICES), s.id
        assert all(re.fullmatch(r"art50_p[1-4]", d) for d in s.duties), s.id
        assert (s.banned != []) == (s.risk == "prohibited"), s.id
        assert not s.basis or s.risk == "high", s.id
        assert set(s.answers) <= questions or all(
            re.match(r"art(5|6|50)_", k) for k in set(s.answers) - questions
        ), s.id
    assert len(ARTICLE_25) == 3  # the art25 answers match one question for all three points


def test_the_quick_subset_covers_every_risk_level_and_both_languages():
    quick = [s for s in load_systems() if s.quick]
    assert 10 <= len(quick) <= 20
    assert {s.risk for s in quick} == set(RISKS) and {s.lang for s in quick} == {"en", "it"}
    assert any(s.basis == ["art6_p1"] for s in quick)  # an Annex I product too


def test_a_high_risk_system_reported_as_minimal_is_under_classified():
    cv = System("cv", "d", "en", "high", basis=["annex3_4"], role="deployer")
    minimal = assess(graph(Facts=[KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[LOW],
                           TransparencyCheck=[NONE]), cv)  # fmt: skip
    high = assess(graph(Facts=[KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[HIGH],
                        TransparencyCheck=[NONE]), cv)  # fmt: skip
    assert (minimal.risk, minimal.under, high.risk, high.under) == ("minimal", True, "high", False)
    assert high.misses() == []  # "annex3_4" accepts the reported 4(a)
    summary = summarise([minimal, high])
    assert (summary.correct, len(summary.under), summary.confusion[("high", "minimal")]) == (
        1, 1, 1,
    )  # fmt: skip


def test_follow_up_questions_are_answered_from_the_case():
    unsure = KNOWN.model_copy(update={"rebranded": None})
    rebranded = KNOWN.model_copy(update={"rebranded": True})
    case = System("x", "d", "en", "high", role="provider_and_deployer",
                  answers={"art25": "We sell it under our brand"})  # fmt: skip
    replies = graph(
        Facts=[unsure, rebranded],
        ProhibitedCheck=[CLEAR] * 2,
        HighRiskCheck=[HIGH] * 2,
        TransparencyCheck=[NONE] * 2,
    )
    outcome = assess(replies, case)
    assert outcome.asked == ["art25"] and outcome.misses() == [] and not outcome.error


def test_details_that_differ_from_the_label_are_listed():
    report = {
        "risk": "high",
        "high_risk_basis": ["it_annex3_5_a"],
        "banned": [],
        "role": "deployer",
        "transparency_duties": [],
        "other_role_duties": [{"chunk_id": "it_art50_p1"}],
    }
    case = System("x", "d", "it", "high", basis=["annex3_5_b"], duties=["art50_p1", "art50_p2"])
    assert Outcome(case, report).misses() == [
        "basis annex3_5_b (got ['annex3_5_a'])",
        "duties ['art50_p2'] (got ['art50_p1'])",
    ]


def test_a_failing_system_is_an_error_not_a_classification():
    def broken(*_):
        raise RuntimeError("daily cap")

    outcome = assess(SimpleNamespace(invoke=broken), System("x", "d", "en", "minimal"))
    assert outcome.error == "RuntimeError: daily cap" and not outcome.under
    assert len(summarise([outcome]).errors) == 1
