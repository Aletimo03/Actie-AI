from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.app.agent.facts import Facts
from backend.app.agent.graph import MAX_ROUNDS, after_facts, after_prohibited, build_graph
from backend.app.agent.prohibited import PRACTICES, ProhibitedCheck, decide
from backend.app.retrieval.contexts import Context

KNOWN = Facts(purpose="Rank CVs", domain="employment", affected_people="people", role="deployer")
UNKNOWN = Facts(summary="Something")
NO = {"applies": "no", "reason": "Does not match."}
CLEAR = ProhibitedCheck(**dict.fromkeys(PRACTICES, NO))
BANNED = ProhibitedCheck(
    **dict.fromkeys(PRACTICES, NO) | {"f": {"applies": "yes", "reason": "Emotions.", "quote": "q"}}
)
UNSURE = ProhibitedCheck(
    **dict.fromkeys(PRACTICES, NO)
    | {"f": {"applies": "uncertain", "reason": "?", "question": "Is it for medical reasons?"}}
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


def run(llm, *resumes, lang="en"):
    """Start an assessment, answer each interrupt in turn, return every step's output."""
    graph = build_graph(llm, fetch, InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}
    outputs = [graph.invoke({"description": "A system.", "lang": lang}, config)]
    for answers in resumes:
        outputs.append(graph.invoke(Command(resume=answers), config))
    return outputs


def test_known_facts_and_no_ban_go_straight_to_the_report():
    llm = ScriptedLLM(Facts=[KNOWN], ProhibitedCheck=[CLEAR])
    [state] = run(llm)
    assert state["report"]["risk"] == "not_prohibited"
    assert state["report"]["citations"] == [] and state["report"]["assumed_unknown"] == []
    assert [name for name, _ in llm.prompts] == ["Facts", "ProhibitedCheck"]


def test_a_ban_ends_with_a_cited_report():
    [state] = run(ScriptedLLM(Facts=[KNOWN], ProhibitedCheck=[BANNED]))
    assert state["report"]["risk"] == "prohibited" and state["report"]["banned"] == ["f"]
    assert state["report"]["citations"][0]["chunk_id"] == "en_art5_p1_f"


def test_missing_facts_pause_for_questions_and_answers_reach_the_prompt():
    llm = ScriptedLLM(Facts=[UNKNOWN, KNOWN], ProhibitedCheck=[CLEAR])
    paused, done = run(llm, {"purpose": "It ranks CVs", "role": ""}, lang="it")
    [interruption] = paused["__interrupt__"]
    asked = interruption.value["questions"]
    assert [q["id"] for q in asked] == ["purpose", "domain", "affected_people", "role"]
    assert asked[0]["text"].startswith("A cosa serve")  # in the user's language
    second_extract = llm.prompts[1][1]
    assert "- A cosa serve il sistema, e cosa produce o decide?: It ranks CVs" in second_extract
    assert "sviluppato" not in second_extract  # empty answers are dropped
    assert done["report"]["risk"] == "not_prohibited"


def test_after_max_rounds_the_report_states_its_assumptions():
    llm = ScriptedLLM(Facts=[UNKNOWN] * (MAX_ROUNDS + 1), ProhibitedCheck=[CLEAR])
    *_, done = run(llm, *[{"purpose": "?"}] * MAX_ROUNDS)
    assert done["rounds"] == MAX_ROUNDS
    assert done["report"]["assumed_unknown"] == ["purpose", "domain", "affected_people", "role"]


def test_an_uncertain_practice_is_asked_then_everything_is_checked_again():
    llm = ScriptedLLM(Facts=[KNOWN, KNOWN], ProhibitedCheck=[UNSURE, BANNED])
    paused, done = run(llm, {"art5_f": "No, it is for grading"})
    assert paused["__interrupt__"][0].value["questions"] == [
        {"id": "art5_f", "text": "Is it for medical reasons?"}
    ]
    assert [name for name, _ in llm.prompts] == ["Facts", "ProhibitedCheck"] * 2
    assert done["report"]["risk"] == "prohibited" and done["report"]["uncertain"] == []


def test_edges_are_plain_functions_of_the_state():
    question = [{"id": "x", "text": "?"}]
    assert after_facts({"questions": question}) == "ask_user"
    assert after_facts({"questions": question, "rounds": MAX_ROUNDS}) == "check_prohibited"
    assert after_facts({"questions": []}) == "check_prohibited"
    assert after_prohibited({"prohibited": decide(BANNED, "en"), "questions": []}) == "report"
    unsure = {"prohibited": decide(UNSURE, "en"), "questions": question}
    assert after_prohibited(unsure) == "ask_user"
    assert after_prohibited(unsure | {"rounds": MAX_ROUNDS}) == "report"
