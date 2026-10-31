"""End-to-end eval: every system in evals/systems.toml through the whole graph.

Each system is assessed as a user would: the graph runs, every follow-up
question is answered from the case's `answers` (or skipped with a blank),
and the final report is compared with the label. The gate is
under-classification: a system reported at a lower risk than its label
(high reported as limited, say) tells a user they have fewer obligations
than they do. It must be 0, and the script exits 1 otherwise.
Over-classification is reported but tolerated: it errs towards caution.

The run costs about 12k tokens per system. With LLM_CACHE_DIR set, a run
stopped by a daily cap resumes for free: every call already answered comes
from the cache.

    uv run --env-file .env python -m evals.systems [--quick] [--only id,id] [--out results.json]

--quick runs the systems marked `quick` (about 15): enough to check a prompt
change in minutes; the full set is for milestones.
"""

import argparse
import json
import os
import sys
import time
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psycopg
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from backend.app.agent.citations import fetch_chunks
from backend.app.agent.graph import SERDE, build_graph
from backend.app.llm import LLM
from backend.app.retrieval.contexts import fetch_contexts

SYSTEMS = Path(__file__).with_name("systems.toml")
RISKS = ["minimal", "limited", "high", "prohibited"]  # increasing obligations
MAX_PAUSES = 5  # more interrupts than the graph's rounds allow means a bug, not a user
# Errors in a row that stop the run: every provider capped or broken (a fallback without
# credits fails at once), so the rest would only fail too. Finished calls stay cached.
STOP_AFTER_ERRORS = 3


@dataclass
class System:
    id: str
    description: str
    lang: str
    risk: str
    banned: list[str] = field(default_factory=list)
    basis: list[str] = field(default_factory=list)
    duties: list[str] = field(default_factory=list)
    role: str | None = None
    answers: dict[str, str] = field(default_factory=dict)
    why: str = ""
    quick: bool = False  # part of the --quick subset


@dataclass
class Outcome:
    system: System
    report: dict | None = None
    error: str | None = None
    asked: list[str] = field(default_factory=list)  # question ids, in order
    seconds: float = 0.0

    @property
    def risk(self) -> str:
        return self.report["risk"] if self.report else "error"

    @property
    def under(self) -> bool:
        """Reported at a lower risk than the label: the gate."""
        return self.report is not None and RISKS.index(self.risk) < RISKS.index(self.system.risk)

    @property
    def over(self) -> bool:
        return self.report is not None and RISKS.index(self.risk) > RISKS.index(self.system.risk)

    def misses(self) -> list[str]:
        """The labelled details the report gets wrong, besides the risk level."""
        if not self.report:
            return []
        report, lang, misses = self.report, self.system.lang, []
        bases = [b.removeprefix(f"{lang}_") for b in report["high_risk_basis"]]
        for expected in self.system.basis:  # "annex3_4" accepts "annex3_4_a"
            if not any(b == expected or b.startswith(f"{expected}_") for b in bases):
                misses.append(f"basis {expected} (got {bases})")
        if missing := set(self.system.banned) - set(report["banned"]):
            misses.append(f"banned {sorted(missing)} (got {report['banned']})")
        duties = report["transparency_duties"] + report["other_role_duties"]
        found = {d["chunk_id"].removeprefix(f"{lang}_") for d in duties}
        if missing := set(self.system.duties) - found:
            misses.append(f"duties {sorted(missing)} (got {sorted(found)})")
        if self.system.role and report["role"] != self.system.role:
            misses.append(f"role {self.system.role} (got {report['role']})")
        return misses


@dataclass
class Summary:
    total: int = 0
    correct: int = 0
    under: list[Outcome] = field(default_factory=list)
    over: list[Outcome] = field(default_factory=list)
    errors: list[Outcome] = field(default_factory=list)
    detail_misses: list[Outcome] = field(default_factory=list)
    confusion: Counter = field(default_factory=Counter)  # (label, reported) -> count
    citations: int = 0
    verified: int = 0


def load_systems(path: Path = SYSTEMS) -> list[System]:
    return [System(**s) for s in tomllib.loads(path.read_text(encoding="utf-8"))["system"]]


def assess(graph, system: System) -> Outcome:
    """Run one system to its report, answering each pause from the case."""
    outcome = Outcome(system)
    config = {"configurable": {"thread_id": system.id}}
    started = time.monotonic()
    try:
        state = graph.invoke({"description": system.description, "lang": system.lang}, config)
        for _ in range(MAX_PAUSES):
            if "__interrupt__" not in state:
                break
            questions = state["__interrupt__"][0].value["questions"]
            outcome.asked += [q["id"] for q in questions]
            # Blank answers skip a question: an empty dict would not resume the run.
            replies = {q["id"]: system.answers.get(q["id"], "") for q in questions}
            state = graph.invoke(Command(resume=replies), config)
        outcome.report = state.get("report")
        if outcome.report is None:
            outcome.error = f"no report after {MAX_PAUSES} pauses"
    except Exception as error:  # one system failing must not stop the run
        outcome.error = f"{type(error).__name__}: {str(error)[:200]}"
    outcome.seconds = time.monotonic() - started
    return outcome


def summarise(outcomes: list[Outcome]) -> Summary:
    summary = Summary(total=len(outcomes))
    for outcome in outcomes:
        summary.confusion[(outcome.system.risk, outcome.risk)] += 1
        if outcome.error:
            summary.errors.append(outcome)
            continue
        summary.correct += outcome.risk == outcome.system.risk
        if outcome.under:
            summary.under.append(outcome)
        if outcome.over:
            summary.over.append(outcome)
        if outcome.misses():
            summary.detail_misses.append(outcome)
        citations = outcome.report["citations"]
        summary.citations += len(citations)
        summary.verified += sum(c["verified"] for c in citations)
    return summary


def print_line(outcome: Outcome) -> None:
    mark = "UNDER" if outcome.under else "over " if outcome.over else "ok   "
    if outcome.error:
        mark = "ERROR"
    asked = f" asked={outcome.asked}" if outcome.asked else ""
    print(f"{mark} {outcome.system.id:<30} want {outcome.system.risk:<10} got {outcome.risk:<10}"
          f" {outcome.seconds:5.0f}s{asked}", flush=True)  # fmt: skip


def print_summary(summary: Summary, usage) -> None:
    graded = summary.total - len(summary.errors)
    share = summary.correct / max(graded, 1)
    print(f"\nrisk level: {summary.correct}/{graded} correct ({share:.0%}), "
          f"{len(summary.under)} under-classified (gate: 0), {len(summary.over)} over, "
          f"{len(summary.errors)} errors")  # fmt: skip
    print("confusion (rows = label, columns = reported):")
    columns = [*RISKS, "error"]
    print(" " * 12 + "".join(f"{c:>11}" for c in columns))
    for label in RISKS:
        print(f"{label:<12}" + "".join(f"{summary.confusion[(label, c)]:>11}" for c in columns))
    if summary.citations:
        share = summary.verified / summary.citations
        print(f"citations: {summary.verified}/{summary.citations} verified ({share:.0%})")
    for outcome in summary.under:
        print(f"  UNDER {outcome.system.id}: {outcome.system.why}")
    for outcome in summary.detail_misses:
        print(f"  details {outcome.system.id}: {'; '.join(outcome.misses())}")
    for outcome in summary.errors:
        print(f"  ERROR {outcome.system.id}: {outcome.error}")
    if usage:
        print(f"tokens: {usage.prompt_tokens} in, {usage.completion_tokens} out, "
              f"{usage.calls} calls, {usage.cache_hits} from cache, "
              f"{usage.fallback_calls} on a fallback, "
              f"{usage.rate_limit_wait:.0f} s waiting for rate limits")  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess every labelled system end to end.")
    parser.add_argument("--quick", action="store_true", help="only the systems marked quick")
    parser.add_argument("--only", help="comma-separated system ids")
    parser.add_argument("--out", type=Path, help="write every outcome as JSON")
    args = parser.parse_args()

    systems = load_systems()
    if args.quick:
        systems = [s for s in systems if s.quick]
    if args.only:
        wanted = set(args.only.split(","))
        systems = [s for s in systems if s.id in wanted]
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    llm = LLM()
    print(f"model {llm.model}, daily-cap fallbacks {llm.fallbacks or 'none'}", flush=True)
    graph = build_graph(
        llm,
        lambda ids: fetch_contexts(conn, ids),
        lambda ids: fetch_chunks(conn, ids),
        InMemorySaver(serde=SERDE),
    )
    outcomes = []
    for system in systems:
        outcome = assess(graph, system)
        outcomes.append(outcome)
        print_line(outcome)
        recent = outcomes[-STOP_AFTER_ERRORS:]
        if len(recent) == STOP_AFTER_ERRORS and all(o.error for o in recent):
            print(f"stopped after {STOP_AFTER_ERRORS} errors in a row ({outcome.error[:80]}). "
                  "Re-run later: with LLM_CACHE_DIR the finished calls cost nothing.",
                  flush=True)  # fmt: skip
            outcomes = outcomes[:-STOP_AFTER_ERRORS]  # not results: the run had stopped working
            break
    summary = summarise(outcomes)
    print_summary(summary, llm.usage)
    if args.out:
        rows = [asdict(o) | {"risk": o.risk, "misses": o.misses()} for o in outcomes]
        args.out.write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    sys.exit(1 if summary.under else 0)


if __name__ == "__main__":
    main()
