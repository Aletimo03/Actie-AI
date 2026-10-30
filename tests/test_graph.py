import logging

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.app.agent.citations import Chunk
from backend.app.agent.facts import Facts
from backend.app.agent.graph import (
    MAX_ROUNDS,
    SERDE,
    after_facts,
    after_high_risk,
    after_prohibited,
    after_role,
    after_transparency,
    build_graph,
)
from backend.app.agent.high_risk import ExceptionFinding, HighRiskCheck
from backend.app.agent.prohibited import PRACTICES, ProhibitedCheck, decide
from backend.app.agent.transparency import RULES, TransparencyCheck
from backend.app.retrieval.contexts import Context

KNOWN = Facts(
    purpose="Rank CVs",
    domain="employment",
    affected_people="people",
    role="deployer",
    rebranded=False,
    substantially_modified=False,
    changed_purpose=False,
)
UNKNOWN = Facts(summary="Something")
NO = {"applies": "no", "reason": "Does not match."}
CLEAR = ProhibitedCheck(**dict.fromkeys(PRACTICES, NO))
BANNED = ProhibitedCheck(
    **dict.fromkeys(PRACTICES, NO)
    | {"f": {"applies": "yes", "reason": "Emotions.", "quote": "the words"}}
)
UNSURE = ProhibitedCheck(
    **dict.fromkeys(PRACTICES, NO)
    | {"f": {"applies": "uncertain", "reason": "?", "question": "Is it for medical reasons?"}}
)
LOW = HighRiskCheck(annex_i=NO, annex_iii=NO, exception=NO)
NONE = TransparencyCheck(**dict.fromkeys(RULES, NO))
CHATBOT = TransparencyCheck(
    **dict.fromkeys(RULES, NO)
    | {"interacts": {"applies": "yes", "reason": "Chats.", "quote": "the words"}}
)
HIGH = HighRiskCheck(
    annex_i=NO,
    annex_iii={"applies": "yes", "point": "4(a)", "reason": "Ranks CVs.", "quote": "The words"},
    exception=NO,
)


class ScriptedLLM:
    """Replies in order per schema, and records every prompt."""

    def __init__(self, **replies):
        self.replies = {name: list(items) for name, items in replies.items()}
        self.prompts: list[tuple[str, str]] = []

    def ask(self, system, user, schema):
        self.prompts.append((schema.__name__, user))
        return self.replies[schema.__name__].pop(0)


def fetch(ids):
    return [Context(i, i, f"text of {i}") for i in ids]


def lookup(ids):
    return [Chunk(i, i, f"{i}: the words of the law") for i in ids]


def run(llm, *resumes, lang="en", lookup=lookup):
    """Start an assessment, answer each interrupt in turn, return every step's output."""
    graph = build_graph(llm, fetch, lookup, InMemorySaver(serde=SERDE))
    config = {"configurable": {"thread_id": "t1"}}
    outputs = [graph.invoke({"description": "A system.", "lang": lang}, config)]
    for answers in resumes:
        outputs.append(graph.invoke(Command(resume=answers), config))
    return outputs


def steps(llm):
    return [name for name, _ in llm.prompts]


def test_no_ban_and_no_annex_match_is_not_high_risk():
    llm = ScriptedLLM(
        Facts=[KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[LOW], TransparencyCheck=[NONE]
    )
    [state] = run(llm)
    assert state["report"]["risk"] == "minimal"
    assert state["report"]["citations"] == [] and state["report"]["assumed_unknown"] == []
    assert steps(llm) == ["Facts", "ProhibitedCheck", "HighRiskCheck", "TransparencyCheck"]


def test_an_annex_iii_match_is_high_risk_with_its_citation():
    [state] = run(
        ScriptedLLM(
            Facts=[KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[HIGH], TransparencyCheck=[NONE]
        )
    )
    assert state["report"]["risk"] == "high"
    assert state["report"]["high_risk_basis"] == ["en_annex3_4_a"]
    [citation] = state["report"]["citations"]
    assert (citation["chunk_id"], citation["verified"]) == ("en_annex3_4_a", True)
    assert state["report"]["unverified"] == []


def test_a_citation_the_law_does_not_back_is_flagged_and_the_verdict_stands():
    def law_without_annex_iii(ids):
        return [c for c in lookup(ids) if "annex3" not in c.id]

    llm = ScriptedLLM(
        Facts=[KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[HIGH], TransparencyCheck=[CHATBOT]
    )
    [state] = run(llm, lookup=law_without_annex_iii)
    assert state["report"]["risk"] == "high"
    assert state["report"]["unverified"] == ["en_annex3_4_a"]
    assert [c["verified"] for c in state["report"]["citations"]] == [False, True]


def test_transparency_duties_alone_make_a_limited_risk_system():
    chatbot_maker = KNOWN.model_copy(update={"role": "provider"})
    llm = ScriptedLLM(
        Facts=[chatbot_maker],
        ProhibitedCheck=[CLEAR],
        HighRiskCheck=[LOW],
        TransparencyCheck=[CHATBOT],
    )
    [state] = run(llm)
    assert state["report"]["risk"] == "limited"
    [duty] = state["report"]["transparency_duties"]
    assert (duty["chunk_id"], duty["who"]) == ("en_art50_p1", "provider")
    assert state["report"]["other_role_duties"] == []


def test_high_risk_systems_also_get_their_transparency_duties():
    llm = ScriptedLLM(
        Facts=[KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[HIGH], TransparencyCheck=[CHATBOT]
    )
    [state] = run(llm)
    assert state["report"]["risk"] == "high"
    # KNOWN is a deployer: the chatbot disclosure is the provider's duty, shown for context
    assert state["report"]["transparency_duties"] == []
    assert state["report"]["other_role_duties"][0]["chunk_id"] == "en_art50_p1"
    assert [c["chunk_id"] for c in state["report"]["citations"]] == ["en_annex3_4_a", "en_art50_p1"]


def test_a_ban_skips_the_high_risk_check():
    llm = ScriptedLLM(Facts=[KNOWN], ProhibitedCheck=[BANNED])
    [state] = run(llm)
    assert state["report"]["risk"] == "prohibited" and state["report"]["banned"] == ["f"]
    assert state["report"]["citations"][0]["chunk_id"] == "en_art5_p1_f"
    assert steps(llm) == ["Facts", "ProhibitedCheck"]


def test_missing_facts_pause_for_questions_and_answers_reach_the_prompt():
    llm = ScriptedLLM(
        Facts=[UNKNOWN, KNOWN],
        ProhibitedCheck=[CLEAR],
        HighRiskCheck=[LOW],
        TransparencyCheck=[NONE],
    )
    paused, done = run(llm, {"purpose": "It ranks CVs", "role": ""}, lang="it")
    [interruption] = paused["__interrupt__"]
    asked = interruption.value["questions"]
    assert [q["id"] for q in asked] == ["purpose", "domain", "affected_people", "role"]
    assert asked[0]["text"].startswith("A cosa serve")  # in the user's language
    second_extract = llm.prompts[1][1]
    assert "- A cosa serve il sistema, e cosa produce o decide?: It ranks CVs" in second_extract
    assert "sviluppato" not in second_extract  # empty answers are dropped
    assert done["report"]["risk"] == "minimal"


def test_after_max_rounds_the_report_states_its_assumptions():
    llm = ScriptedLLM(
        Facts=[UNKNOWN] * (MAX_ROUNDS + 1),
        ProhibitedCheck=[CLEAR],
        HighRiskCheck=[LOW],
        TransparencyCheck=[NONE],
    )
    *_, done = run(llm, *[{"purpose": "?"}] * MAX_ROUNDS)
    assert done["rounds"] == MAX_ROUNDS
    assert done["report"]["assumed_unknown"] == ["purpose", "domain", "affected_people", "role"]


def test_an_uncertain_practice_is_asked_then_everything_is_checked_again():
    llm = ScriptedLLM(Facts=[KNOWN, KNOWN], ProhibitedCheck=[UNSURE, BANNED])
    paused, done = run(llm, {"art5_f": "No, it is for grading"})
    assert paused["__interrupt__"][0].value["questions"] == [
        {"id": "art5_f", "text": "Is it for medical reasons?"}
    ]
    assert steps(llm) == ["Facts", "ProhibitedCheck"] * 2
    assert done["report"]["risk"] == "prohibited" and done["report"]["uncertain"] == []


def test_an_open_profiling_question_is_asked_and_counts_as_high_risk_meanwhile():
    narrow = ExceptionFinding(applies="yes", condition="a", reason="Narrow task.")
    excepted = HIGH.model_copy(update={"exception": narrow})
    rounds = MAX_ROUNDS + 1
    llm = ScriptedLLM(
        Facts=[KNOWN] * rounds,
        ProhibitedCheck=[CLEAR] * rounds,
        HighRiskCheck=[excepted] * rounds,
        TransparencyCheck=[NONE] * rounds,
    )
    skipped = {"art6_profiling": ""}  # the user leaves the question blank every time
    paused, *_, done = run(llm, *[skipped] * MAX_ROUNDS)
    assert paused["__interrupt__"][0].value["questions"][0]["id"] == "art6_profiling"
    assert done["report"]["risk"] == "high" and done["report"]["uncertain"] == ["profiling"]


def test_checkpoints_rebuild_only_registered_types(caplog):
    llm = ScriptedLLM(
        Facts=[UNKNOWN, KNOWN],
        ProhibitedCheck=[CLEAR],
        HighRiskCheck=[LOW],
        TransparencyCheck=[NONE],
    )
    with caplog.at_level(logging.WARNING):
        run(llm, {"purpose": "It ranks CVs"})
    assert "unregistered type" not in caplog.text


def test_edges_are_plain_functions_of_the_state():
    question = [{"id": "x", "text": "?"}]
    assert after_facts({"questions": question}) == "ask_user"
    assert after_facts({"questions": question, "rounds": MAX_ROUNDS}) == "check_prohibited"
    assert after_facts({"questions": []}) == "check_prohibited"
    banned = {"prohibited": decide(BANNED, "en"), "questions": []}
    assert after_prohibited(banned) == "verify_citations"
    unsure = {"prohibited": decide(UNSURE, "en"), "questions": question}
    assert after_prohibited(unsure) == "ask_user"
    assert after_prohibited(unsure | {"rounds": MAX_ROUNDS}) == "check_high_risk"
    assert after_high_risk({"questions": question}) == "ask_user"
    assert after_high_risk({"questions": []}) == "check_transparency"
    assert after_transparency({"questions": question}) == "ask_user"
    assert after_transparency({"questions": []}) == "determine_role"
    assert after_role({"questions": question}) == "ask_user"
    assert after_role({"questions": []}) == "verify_citations"


def test_a_deployer_of_a_high_risk_system_is_asked_about_article_25_and_becomes_provider():
    unsure = KNOWN.model_copy(update={"rebranded": None, "substantially_modified": None})
    rebranded = KNOWN.model_copy(update={"rebranded": True})
    llm = ScriptedLLM(
        Facts=[unsure, rebranded],
        ProhibitedCheck=[CLEAR, CLEAR],
        HighRiskCheck=[HIGH, HIGH],
        TransparencyCheck=[NONE, NONE],
    )
    paused, done = run(llm, {"art25": "We sell it under our brand"})
    [question] = paused["__interrupt__"][0].value["questions"]
    assert question["id"] == "art25" and "trademark" in question["text"]
    report = done["report"]
    assert (report["role"], report["became_provider"]) == ("provider_and_deployer", ["a"])
    assert "en_art25_p1_a" in [c["chunk_id"] for c in report["citations"]]


def test_a_minimal_risk_deployer_is_not_asked_about_article_25():
    deployer = KNOWN.model_copy(update={"rebranded": None})
    llm = ScriptedLLM(
        Facts=[deployer], ProhibitedCheck=[CLEAR], HighRiskCheck=[LOW], TransparencyCheck=[NONE]
    )
    [state] = run(llm)
    assert (state["report"]["role"], state["report"]["uncertain"]) == ("deployer", [])
