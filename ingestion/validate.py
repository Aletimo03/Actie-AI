"""Validate stage: the gate between chunking and loading.

Every check reads the parsed nodes, chunks and contexts of both languages and
returns its problems. Any problem fails the gate (exit code 1), so a broken
parse never reaches the database. The same checks run as tests in CI.
"""

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ingestion.chunk import latest_processed

LANGS = ("en", "it")
EXPECTED_COUNTS = {"article": 119, "annex": 14, "recital": 180}  # consolidated text of 27.7.2026
MAX_EMBED_WORDS = 1500  # bge-m3 reads 8192 tokens; anything near this means a parsing error
MAX_CONTEXT_WORDS = 3000  # what one context may cost in an LLM prompt
FORBIDDEN = {"▼": "amendment marker", "()": "empty footnote marker", "\xa0": "non-breaking space"}
SPOT_CHECKS = {  # id suffix -> words that text must contain, per language
    "art5_p1_f": {"en": "emotions", "it": "emozioni"},
    "annex3_4_a": {"en": "recruitment", "it": "assunzione"},
    "annex3_5_b": {"en": "creditworthiness", "it": "affidabilità creditizia"},
    "art113_c_i": {"en": "2 December 2027", "it": "2 dicembre 2027"},
    "art6_p3_a": {"en": "narrow procedural task", "it": "procedurale limitato"},
}
SHOWN = 5  # offending ids listed per check


@dataclass
class Check:
    name: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class Data:
    nodes: dict[str, list[dict]]  # per language
    chunks: dict[str, list[dict]]
    contexts: dict[str, list[dict]]


def load(folder: Path) -> Data:
    def read(name: str) -> list[dict]:
        return [
            json.loads(line) for line in (folder / name).read_text(encoding="utf-8").splitlines()
        ]

    return Data(
        nodes={lang: read(f"{lang}.jsonl") for lang in LANGS},
        chunks={lang: read(f"chunks_{lang}.jsonl") for lang in LANGS},
        contexts={lang: read(f"contexts_{lang}.jsonl") for lang in LANGS},
    )


def check_counts(data: Data) -> Check:
    check = Check("counts: 119 articles, 14 annexes, 180 recitals")
    for lang, nodes in data.nodes.items():
        counts = Counter(n["kind"] for n in nodes)
        for kind, expected in EXPECTED_COUNTS.items():
            if counts[kind] != expected:
                check.problems.append(f"{lang}: {counts[kind]} {kind}s, expected {expected}")
    return check


def check_twins(data: Data) -> Check:
    """Every English chunk and context has its Italian twin, with the same amended flag."""
    check = Check("twins: en and it have the same chunks and contexts")
    for table in ("chunks", "contexts"):
        en, it = ({r["id"][3:]: r for r in getattr(data, table)[lang]} for lang in LANGS)
        for missing, side in ((en.keys() - it.keys(), "it"), (it.keys() - en.keys(), "en")):
            check.problems += [f"{table}: no {side} twin for {key}" for key in sorted(missing)]
    en, it = ({r["id"][3:]: r["amended"] for r in data.chunks[lang]} for lang in LANGS)
    check.problems += [
        f"amended differs: {k}" for k in sorted(en.keys() & it.keys()) if en[k] != it[k]
    ]
    return check


def check_ids(data: Data) -> Check:
    check = Check("ids: unique, and every chunk's context exists")
    for lang in LANGS:
        for table in ("nodes", "chunks", "contexts"):
            counts = Counter(r["id"] for r in getattr(data, table)[lang])
            check.problems += [f"{table}: duplicate {i}" for i, n in counts.items() if n > 1]
        context_ids = {c["id"] for c in data.contexts[lang]}
        check.problems += [
            f"{c['id']}: unknown context {c['context_id']}"
            for c in data.chunks[lang]
            if c["context_id"] not in context_ids
        ]
    return check


def check_sizes(data: Data) -> Check:
    check = Check(
        f"sizes: no empty chunk, chunks <= {MAX_EMBED_WORDS} words, contexts <= {MAX_CONTEXT_WORDS}"
    )
    for lang in LANGS:
        for c in data.chunks[lang]:
            words = len(c["embed_text"].split())
            if not c["text"].strip():
                check.problems.append(f"{c['id']}: empty text")
            elif words > MAX_EMBED_WORDS:
                check.problems.append(f"{c['id']}: {words} words to embed")
        for c in data.contexts[lang]:
            words = len(c["text"].split())
            if words > MAX_CONTEXT_WORDS:
                check.problems.append(f"{c['id']}: context of {words} words")
    return check


def check_refs(data: Data) -> Check:
    check = Check("refs: every cross-reference points to an article or annex that exists")
    for lang in LANGS:
        targets = {
            f"art{n['id'].split('_art', 1)[1]}" for n in data.nodes[lang] if n["kind"] == "article"
        }
        targets |= {
            f"annex{n['id'].split('_annex', 1)[1]}"
            for n in data.nodes[lang]
            if n["kind"] == "annex"
        }
        check.problems += [
            f"{c['id']}: unknown ref {ref}"
            for c in data.chunks[lang]
            for ref in c["refs"]
            if ref not in targets
        ]
    return check


def check_clean_text(data: Data) -> Check:
    check = Check("text: no amendment markers, empty footnotes or odd spaces")
    for lang in LANGS:
        for c in data.chunks[lang] + data.contexts[lang]:
            for token, what in FORBIDDEN.items():
                if token in c["text"]:
                    check.problems.append(f"{c['id']}: {what}")
    return check


def check_spot(data: Data) -> Check:
    check = Check("spot checks: known provisions say what the law says")
    for lang in LANGS:
        text = {c["id"]: c["text"] for c in data.chunks[lang]}
        for suffix, words in SPOT_CHECKS.items():
            chunk_id = f"{lang}_{suffix}"
            if chunk_id not in text:
                check.problems.append(f"{chunk_id}: missing")
            elif words[lang].lower() not in text[chunk_id].lower():
                check.problems.append(f"{chunk_id}: does not mention '{words[lang]}'")
    return check


CHECKS = [
    check_counts,
    check_twins,
    check_ids,
    check_sizes,
    check_refs,
    check_clean_text,
    check_spot,
]


def validate(data: Data) -> list[Check]:
    return [run(data) for run in CHECKS]


def main() -> None:
    folder = latest_processed()
    results = validate(load(folder))
    for check in results:
        print(f"{'PASS' if check.ok else 'FAIL'}  {check.name}")
        for problem in check.problems[:SHOWN]:
            print(f"      - {problem}")
        if len(check.problems) > SHOWN:
            print(f"      … and {len(check.problems) - SHOWN} more")
    failed = sum(not c.ok for c in results)
    print(f"\n{folder.name}: {len(results) - failed}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
