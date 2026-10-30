"""The assessment as a LangGraph state machine (Lecture 06).

    START -> extract_facts --(facts missing)--> ask_user -> extract_facts
                  |
                  v
           check_prohibited --(uncertain)--> ask_user -> extract_facts
                  |      \
                  |       (prohibited)--> report
                  v
           check_high_risk --(uncertain)--> ask_user -> extract_facts
                  |
                  v
               report -> END

The LLM fills schemas inside the nodes; the edges are plain functions of the
state, so every branch is decided by code. ask_user pauses the run with
interrupt(): the questions go to the caller, and the run resumes from the
checkpoint when the answers come back (Command(resume={question id: answer})).
After the answers the facts are extracted again and the checks run again, so
each check keeps only its latest result and report collects citations from
those, never from earlier, possibly stale runs.
"""

from collections.abc import Callable
from typing import TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.app.agent.facts import Facts, extract_facts, missing_facts
from backend.app.agent.high_risk import (
    AnnexIIIFinding,
    ExceptionFinding,
    HighRiskCheck,
    HighRiskResult,
    ProductFinding,
    check_high_risk,
)
from backend.app.agent.prohibited import (
    Citation,
    Finding,
    ProhibitedCheck,
    ProhibitedResult,
    check_prohibited,
)
from backend.app.llm import StructuredLLM
from backend.app.retrieval.contexts import Context

# The classes the state holds. A checkpoint may rebuild only these, not any type it names.
STATE_TYPES = [
    (cls.__module__, cls.__name__)
    for cls in (
        Facts,
        Citation,
        Finding,
        ProhibitedCheck,
        ProhibitedResult,
        ProductFinding,
        AnnexIIIFinding,
        ExceptionFinding,
        HighRiskCheck,
        HighRiskResult,
    )
]
SERDE = JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)  # use for every checkpointer

MAX_ROUNDS = 2  # follow-up rounds before the report states its assumptions instead

QUESTIONS = {
    "purpose": {
        "en": "What is the system for, and what does it produce or decide?",
        "it": "A cosa serve il sistema, e cosa produce o decide?",
    },
    "domain": {
        "en": "In which area is it used (e.g. hiring, education, credit, healthcare, "
        "public services)?",
        "it": "In quale ambito viene usato (es. selezione del personale, istruzione, credito, "
        "sanità, servizi pubblici)?",
    },
    "affected_people": {
        "en": "Who is affected by its outputs (e.g. customers, employees, students, the public)?",
        "it": "Chi riguardano i suoi risultati (es. clienti, dipendenti, studenti, cittadini)?",
    },
    "role": {
        "en": "Did you build the system, or do you use one built by someone else?",
        "it": "Il sistema l'avete sviluppato voi, o ne usate uno sviluppato da altri?",
    },
    "real_time": {
        "en": "Does it identify people live, while they are being recorded?",
        "it": "Identifica le persone in tempo reale, mentre vengono riprese?",
    },
}


class Question(TypedDict):
    id: str
    text: str


class Assessment(TypedDict, total=False):
    description: str
    lang: str
    answers: dict[str, str]  # question text -> the user's answer, across all rounds
    rounds: int
    questions: list[Question]  # pending: set by a node, asked by ask_user
    facts: Facts
    prohibited: ProhibitedResult
    high_risk: HighRiskResult
    report: dict


def needs_answers(state: Assessment) -> bool:
    return bool(state.get("questions")) and state.get("rounds", 0) < MAX_ROUNDS


def after_facts(state: Assessment) -> str:
    return "ask_user" if needs_answers(state) else "check_prohibited"


def after_prohibited(state: Assessment) -> str:
    if state["prohibited"].is_prohibited:
        return "report"  # a ban ends the assessment: nothing else can make it lawful
    return "ask_user" if needs_answers(state) else "check_high_risk"


def after_high_risk(state: Assessment) -> str:
    return "ask_user" if needs_answers(state) else "report"


def report(state: Assessment) -> dict:
    prohibited, high_risk = state["prohibited"], state.get("high_risk")
    if prohibited.is_prohibited:
        risk, results = "prohibited", [prohibited]
    else:
        risk = "high" if high_risk.is_high_risk else "not_high_risk"
        results = [prohibited, high_risk]
    return {
        "report": {
            "risk": risk,
            "banned": prohibited.banned,
            "high_risk_basis": [] if prohibited.is_prohibited else high_risk.basis,
            "exception": None if prohibited.is_prohibited else high_risk.exception,
            "uncertain": [name for r in results for name in r.uncertain],
            "assumed_unknown": missing_facts(state["facts"]),
            "citations": [c.model_dump() for r in results for c in r.citations],
        }
    }


def build_graph(llm: StructuredLLM, fetch: Callable[[list[str]], list[Context]], checkpointer=None):
    def extract_facts_node(state: Assessment) -> dict:
        facts = extract_facts(llm, state["description"], state.get("answers"))
        questions = [
            Question(id=name, text=QUESTIONS[name][state["lang"]]) for name in missing_facts(facts)
        ]
        return {"facts": facts, "questions": questions}

    def check_prohibited_node(state: Assessment) -> dict:
        result = check_prohibited(llm, fetch, state["description"], state["facts"], state["lang"])
        questions = [
            Question(id=f"art5_{label}", text=text)
            for label, text in zip(result.uncertain, result.questions, strict=True)
        ]
        return {"prohibited": result, "questions": questions}

    def check_high_risk_node(state: Assessment) -> dict:
        result = check_high_risk(llm, fetch, state["description"], state["facts"], state["lang"])
        questions = [
            Question(id=f"art6_{name}", text=text)
            for name, text in zip(result.uncertain, result.questions, strict=True)
        ]
        return {"high_risk": result, "questions": questions}

    def ask_user(state: Assessment) -> dict:
        # On resume this node runs again from the top and interrupt() returns the answers,
        # so nothing before it may have side effects. To skip, resume with blank answers
        # ({"role": ""}): an empty dict is not taken as a resume value.
        replies = interrupt({"questions": state["questions"]})
        texts = {q["id"]: q["text"] for q in state["questions"]}
        answered = {texts[i]: answer for i, answer in replies.items() if i in texts and answer}
        return {
            "answers": state.get("answers", {}) | answered,
            "rounds": state.get("rounds", 0) + 1,
            "questions": [],
        }

    graph = StateGraph(Assessment)
    graph.add_node("extract_facts", extract_facts_node)
    graph.add_node("ask_user", ask_user)
    graph.add_node("check_prohibited", check_prohibited_node)
    graph.add_node("check_high_risk", check_high_risk_node)
    graph.add_node("report", report)
    graph.add_edge(START, "extract_facts")
    graph.add_conditional_edges("extract_facts", after_facts, ["ask_user", "check_prohibited"])
    graph.add_conditional_edges(
        "check_prohibited", after_prohibited, ["ask_user", "check_high_risk", "report"]
    )
    graph.add_conditional_edges("check_high_risk", after_high_risk, ["ask_user", "report"])
    graph.add_edge("ask_user", "extract_facts")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)
