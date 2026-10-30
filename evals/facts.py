"""Score extract_facts on evals/facts_cases.toml.

Each case lists the facts that must come out (`expect`) and the facts that
must stay null (`unknown`). A check is one (case, field) pair; a case passes
when all its checks pass. With --runs N every case is extracted N times,
because the same prompt can give different answers.

    uv run --env-file .env python -m evals.facts [--model ollama_chat/gemma4:12b] [--runs 3]
"""

import argparse
import time
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.agent.facts import Facts, extract_facts
from backend.app.llm import LLM, LLM_MODEL, SchemaError

CASES = Path(__file__).with_name("facts_cases.toml")

Extract = Callable[[str], Facts | None]  # description -> facts, None if the call failed


@dataclass
class Case:
    description: str
    lang: str
    expect: dict = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)

    def checks(self) -> dict[str, list]:
        """Field -> acceptable values (None for a fact that must stay unknown)."""
        wanted = {name: v if isinstance(v, list) else [v] for name, v in self.expect.items()}
        return wanted | {name: [None] for name in self.unknown}


@dataclass
class Failure:
    case: Case
    field: str
    got: object


@dataclass
class Score:
    checks: int = 0
    passed: int = 0
    cases: int = 0
    cases_passed: int = 0
    errors: int = 0  # calls that produced no valid Facts at all
    by_field: Counter = field(default_factory=Counter)  # field -> failures
    failures: list[Failure] = field(default_factory=list)


def load_cases(path: Path = CASES) -> list[Case]:
    return [Case(**c) for c in tomllib.loads(path.read_text(encoding="utf-8"))["case"]]


def score(extract: Extract, cases: list[Case], runs: int = 1) -> Score:
    result = Score()
    for _ in range(runs):
        for case in cases:
            facts = extract(case.description)
            result.cases += 1
            if facts is None:
                result.errors += 1
            ok = facts is not None
            for name, accepted in case.checks().items():
                result.checks += 1
                got = getattr(facts, name) if facts else "<error>"
                if got in accepted:
                    result.passed += 1
                else:
                    ok = False
                    result.by_field[name] += 1
                    result.failures.append(Failure(case, name, got))
            result.cases_passed += ok
    return result


def report(model: str, result: Score, seconds: float) -> None:
    print(f"{model}: {result.passed}/{result.checks} checks ({result.passed / result.checks:.0%}), "
          f"{result.cases_passed}/{result.cases} cases, {result.errors} errors, "
          f"{seconds / result.cases:.1f} s per description")  # fmt: skip
    if result.by_field:
        print("  failures by field: " + ", ".join(f"{k} {v}" for k, v in result.by_field.items()))
    for f in result.failures:
        print(f"  - {f.field}: got {f.got!r}, want {f.case.checks()[f.field]}  <- "
              f"{f.case.description[:70]}")  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description="Score extract_facts on the facts test set.")
    parser.add_argument("--model", default=LLM_MODEL)
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    llm = LLM(model=args.model)

    def extract(description: str) -> Facts | None:
        try:
            return extract_facts(llm, description)
        except SchemaError:
            return None

    started = time.monotonic()
    result = score(extract, load_cases(), args.runs)
    report(args.model, result, time.monotonic() - started)
    print(f"  tokens: {llm.usage.prompt_tokens} in, {llm.usage.completion_tokens} out, "
          f"{llm.usage.calls} calls")  # fmt: skip


if __name__ == "__main__":
    main()
