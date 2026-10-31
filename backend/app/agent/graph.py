"""The assessment as a LangGraph state machine (Lecture 06).

    START -> extract_facts --(facts missing)--> ask_user -> extract_facts
                  |
                  v
           check_prohibited --(uncertain)--> ask_user -> extract_facts
                  |      \
                  |       (prohibited)--> verify_citations
                  v
           check_high_risk --(uncertain)--> ask_user -> extract_facts
                  |
                  v
           check_transparency --(uncertain)--> ask_user -> extract_facts
                  |
                  v
           determine_role --(Art. 25 unknown)--> ask_user -> extract_facts
                  |
                  v
           list_obligations -> verify_citations -> report -> END

The LLM fills schemas inside the nodes; the edges are plain functions of the
state, so every branch is decided by code. ask_user pauses the run with
interrupt(): the questions go to the caller, and the run resumes from the
checkpoint when the answers come back (Command(resume={question id: answer})).
After the answers the facts are extracted again and the checks run again, so
each check keeps only its latest result and verify_citations collects the
citations from those, never from earlier, possibly stale runs, and checks
each quote against the law text before the report shows it.
"""

import dataclasses
from collections.abc import Callable
from datetime import date
from typing import TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from backend.app.agent.citations import Chunk, existing, verify
from backend.app.agent.facts import Facts, extract_facts, missing_facts
from backend.app.agent.high_risk import (
    AnnexIIIFinding,
    ExceptionFinding,
    HighRiskCheck,
    HighRiskResult,
    ProductFinding,
    check_high_risk,
)
from backend.app.agent.obligations import Obligation, ObligationsResult, decide_obligations
from backend.app.agent.prohibited import (
    Citation,
    Finding,
    ProhibitedCheck,
    ProhibitedResult,
    check_prohibited,
)
from backend.app.agent.role import RoleResult, decide_role
from backend.app.agent.transparency import (
    Duty,
    TransparencyCheck,
    TransparencyResult,
    check_transparency,
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
        TransparencyCheck,
        TransparencyResult,
        Duty,
        RoleResult,
        Obligation,
        ObligationsResult,
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
    transparency: TransparencyResult
    role: RoleResult
    obligations: ObligationsResult
    citations: list[Citation]  # from the latest results, verified
    report: dict


def needs_answers(state: Assessment) -> bool:
    return bool(state.get("questions")) and state.get("rounds", 0) < MAX_ROUNDS


def after_facts(state: Assessment) -> str:
    return "ask_user" if needs_answers(state) else "check_prohibited"


def after_prohibited(state: Assessment) -> str:
    if state["prohibited"].is_prohibited:
        return "verify_citations"  # a ban ends the assessment: nothing else can make it lawful
    return "ask_user" if needs_answers(state) else "check_high_risk"


def after_high_risk(state: Assessment) -> str:
    return "ask_user" if needs_answers(state) else "check_transparency"


def after_transparency(state: Assessment) -> str:
    return "ask_user" if needs_answers(state) else "determine_role"


def after_role(state: Assessment) -> str:
    return "ask_user" if needs_answers(state) else "list_obligations"


def risk_level(state: Assessment) -> str:
    """prohibited > high > limited (transparency duties only) > minimal."""
    if state["prohibited"].is_prohibited:
        return "prohibited"
    if state["high_risk"].is_high_risk:
        return "high"
    transparency = state["transparency"]
    return "limited" if transparency.duties or transparency.others else "minimal"


def latest_results(state: Assessment) -> list:
    """The results the report rests on: a ban ends the assessment after Article 5."""
    if state["prohibited"].is_prohibited:
        return [state["prohibited"]]
    return [
        state["prohibited"],
        state["high_risk"],
        state["transparency"],
        state["role"],
        state["obligations"],
    ]


def report(state: Assessment) -> dict:
    prohibited = state["prohibited"]
    risk = risk_level(state)
    results = latest_results(state)
    if risk == "prohibited":
        high_risk, transparency = None, None
    else:
        high_risk, transparency = state["high_risk"], state["transparency"]
    citations = state["citations"]
    obligations = state["obligations"] if risk != "prohibited" else ObligationsResult()
    return {
        "report": {
            "risk": risk,
            "role": state["role"].role if "role" in state else state["facts"].role,
            "became_provider": state["role"].became_provider if "role" in state else [],
            "banned": prohibited.banned,
            "high_risk_basis": high_risk.basis if high_risk else [],
            "exception": high_risk.exception if high_risk else None,
            "transparency_duties": [vars(d) for d in transparency.duties] if transparency else [],
            "other_role_duties": [vars(d) for d in transparency.others] if transparency else [],
            "uncertain": [name for r in results for name in r.uncertain],
            "assumed_unknown": missing_facts(state["facts"]),
            "obligations": [
                vars(o) | {"applies_from": o.applies_from.isoformat()}
                for o in obligations.obligations
            ],
            "notes": obligations.notes,
            "citations": [c.model_dump() for c in citations],
            "unverified": [c.chunk_id for c in citations if not c.verified]
            + [o.chunk_id for o in obligations.obligations if not o.verified],
        }
    }


def build_graph(
    llm: StructuredLLM,
    fetch: Callable[[list[str]], list[Context]],
    lookup: Callable[[list[str]], list[Chunk]],
    checkpointer=None,
    today: Callable[[], date] = date.today,
):
    def described(state: Assessment) -> str:
        """The description plus every answer so far, for the checks to read as user data.

        Facts has no field for most legal follow-ups (which 5(1)(h) objective, whether
        the output shapes the decision), so a check that saw only the description kept
        asking the same question: measured on live-face-recognition-police.
        """
        answers = state.get("answers")
        if not answers:
            return state["description"]
        lines = "\n".join(f"- {question}: {answer}" for question, answer in answers.items())
        return f"{state['description'].strip()}\n\nFollow-up answers:\n{lines}"

    def extract_facts_node(state: Assessment) -> dict:
        facts = extract_facts(llm, state["description"], state.get("answers"))
        questions = [
            Question(id=name, text=QUESTIONS[name][state["lang"]]) for name in missing_facts(facts)
        ]
        return {"facts": facts, "questions": questions}

    def check_prohibited_node(state: Assessment) -> dict:
        result = check_prohibited(llm, fetch, described(state), state["facts"], state["lang"])
        questions = [
            Question(id=f"art5_{label}", text=text)
            for label, text in zip(result.uncertain, result.questions, strict=True)
        ]
        return {"prohibited": result, "questions": questions}

    def check_high_risk_node(state: Assessment) -> dict:
        result = check_high_risk(llm, fetch, described(state), state["facts"], state["lang"])
        questions = [
            Question(id=f"art6_{name}", text=text)
            for name, text in zip(result.uncertain, result.questions, strict=True)
        ]
        return {"high_risk": result, "questions": questions}

    def check_transparency_node(state: Assessment) -> dict:
        result = check_transparency(llm, fetch, described(state), state["facts"], state["lang"])
        questions = [
            Question(id=f"art50_{name}", text=text)
            for name, text in zip(result.uncertain, result.questions, strict=True)
        ]
        return {"transparency": result, "questions": questions}

    def determine_role(state: Assessment) -> dict:
        result = decide_role(state["facts"], state["high_risk"].is_high_risk, state["lang"])
        questions = [
            Question(id=name, text=text)
            for name, text in zip(result.uncertain, result.questions, strict=True)
        ]
        return {"role": result, "questions": questions}

    def list_obligations(state: Assessment) -> dict:
        duties = state["transparency"].duties
        basis = state["high_risk"].basis
        result = decide_obligations(state["role"].role, basis, duties, state["lang"], today())
        return {"obligations": result}

    def verify_citations(state: Assessment) -> dict:
        cited = [c for r in latest_results(state) for c in r.citations]
        update = {"citations": verify(cited, lookup)}
        if not state["prohibited"].is_prohibited:
            result = state["obligations"]
            found = existing([o.chunk_id for o in result.obligations], lookup)
            checked = [
                dataclasses.replace(o, verified=o.chunk_id in found) for o in result.obligations
            ]
            update["obligations"] = dataclasses.replace(result, obligations=checked)
        return update

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
    graph.add_node("check_transparency", check_transparency_node)
    graph.add_node("determine_role", determine_role)
    graph.add_node("list_obligations", list_obligations)
    graph.add_node("verify_citations", verify_citations)
    graph.add_node("report", report)
    graph.add_edge(START, "extract_facts")
    graph.add_conditional_edges("extract_facts", after_facts, ["ask_user", "check_prohibited"])
    graph.add_conditional_edges(
        "check_prohibited", after_prohibited, ["ask_user", "check_high_risk", "verify_citations"]
    )
    graph.add_conditional_edges(
        "check_high_risk", after_high_risk, ["ask_user", "check_transparency"]
    )
    graph.add_conditional_edges(
        "check_transparency", after_transparency, ["ask_user", "determine_role"]
    )
    graph.add_conditional_edges("determine_role", after_role, ["ask_user", "list_obligations"])
    graph.add_edge("list_obligations", "verify_citations")
    graph.add_edge("ask_user", "extract_facts")
    graph.add_edge("verify_citations", "report")
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)
