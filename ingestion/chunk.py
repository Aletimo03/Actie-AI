"""Chunk stage: parsed nodes -> search chunks and context units.

Two layers ("search small, read big"):

- A search chunk is one node with its own text (a paragraph, a point, a
  recital...). It is what gets embedded, so its embed_text carries a context
  header ("AI Act > Chapter III > ... > Article 6 Classification rules ... >
  3 > (a)") and, for points, the opening line of the parent, so that a bare
  "terrorism," still says what list it belongs to.
- A context unit is what the LLM reads: the enclosing paragraph with all its
  points, or for articles without numbered paragraphs and for annexes the
  top-level point, or the recital itself. Every chunk names its context_id.
"""

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ingestion.parse import PROCESSED_DIR, roman_to_int

ACT_NAME = {"en": "AI Act", "it": "Regolamento IA"}
# The parser writes chapter and annex-section labels in English; headers use the chunk's language.
LOCAL_WORDS = {"it": {"Chapter": "Capo", "Section": "Sezione"}}
LEAD_IN_WORDS = 60  # longest parent opening line copied into a point's embed_text

# Cross-references to this Act. Mentions of other acts ("Article 9 of Regulation (EU) 2016/679",
# "Article 4(2) TEU") are skipped by looking at the words right after the number.
REF_PATTERNS = {
    "art": re.compile(r"\b(?:Articles?|articol[oi])\s+(\d+[a-z]?)\b", re.IGNORECASE),
    "annex": re.compile(r"\b(?:Annex(?:es)?|allegat[oi])\s+([IVX]+)\b", re.IGNORECASE),
}
OTHER_ACT = re.compile(
    r"^[\s\d()a-z,]*?(?:of|del|della|dello|dei)\s+(?:the\s+)?"
    r"(?:Regulation|Directive|Decision|Treaty|Protocol|regolamento|direttiva|decisione|trattato|protocollo)"
    r"|^[\s\d()]*(?:TEU|TFEU|TUE|TFUE)\b",
    re.IGNORECASE,
)


@dataclass
class Chunk:
    id: str  # same as the node id, e.g. "en_art6_p3_a"
    lang: str
    kind: str
    header: str
    text: str  # the node's own words, as in the law
    embed_text: str  # header + lead-in + text: what the embedding model sees
    context_id: str  # the context unit the LLM reads
    article: str = ""  # "6", "4a"; empty for annexes and recitals
    paragraph: str = ""  # "3", "1a"
    annex: str = ""  # "III"
    chapter: str = ""
    refs: list[str] = field(default_factory=list)  # ["art6", "annex3"]
    binding: bool = True  # recitals explain the law but do not bind
    amended: bool = False
    source: str = ""


@dataclass
class Context:
    id: str
    lang: str
    header: str
    text: str  # the unit with all its points, labels included
    source: str = ""


class Chunker:
    def __init__(self, nodes: list[dict], lang: str):
        self.lang = lang
        self.nodes = {n["id"]: n for n in nodes}
        self.children: dict[str, list[dict]] = {}
        for node in nodes:  # file order is reading order
            if node["parent_id"]:
                self.children.setdefault(node["parent_id"], []).append(node)

    def ancestors(self, node: dict) -> list[dict]:
        """From the top-level node down to node itself."""
        chain = [node]
        while chain[0]["parent_id"]:
            chain.insert(0, self.nodes[chain[0]["parent_id"]])
        return chain

    def context_of(self, node: dict) -> dict:
        """The unit the LLM reads for this node (see module docstring)."""
        if node["kind"] != "point":
            return node
        top = node
        while self.nodes[top["parent_id"]]["kind"] == "point":
            top = self.nodes[top["parent_id"]]
        parent = self.nodes[top["parent_id"]]
        return parent if parent["kind"] == "paragraph" else top

    def header(self, node: dict) -> str:
        chain = self.ancestors(node)
        # Chapter and section are not nodes: they are the path entries before the first ancestor.
        outer = node["path"][: len(node["path"]) - len(chain)]
        parts = [ACT_NAME[self.lang], *outer]
        for item in chain:
            if item["kind"] in ("article", "annex", "annex_section") and item["title"]:
                parts.append(f"{item['label']} {item['title']}")
            else:
                parts.append(item["label"])
        words = LOCAL_WORDS.get(self.lang, {})
        parts = [re.sub(r"^(\w+)", lambda m: words.get(m.group(1), m.group(1)), p) for p in parts]
        return " › ".join(parts)

    def lead_in(self, node: dict) -> str:
        """The parent's text right before this point's list, e.g. '... any of the following:'."""
        if node["kind"] != "point":
            return ""
        last_text = ""
        for part_kind, value in self.nodes[node["parent_id"]]["parts"]:
            if part_kind == "c" and value == node["id"]:
                break
            if part_kind == "t":
                last_text = value
        words = last_text.split()
        return " ".join(words[:LEAD_IN_WORDS]) + (" …" if len(words) > LEAD_IN_WORDS else "")

    def render(self, node: dict, depth: int = 0, with_children: bool = True) -> str:
        """A unit as readable text in the law's order: text and points interleaved, indented."""
        indent = "  " * depth
        label = "" if node["kind"] in ("article", "annex", "recital") else f"{node['label']} "
        parts = node["parts"] or [["t", node["text"]]]
        lines = []
        for part_kind, value in parts:
            if part_kind == "t":
                lines.append(f"{indent}{'' if lines else label}{value}")
            elif with_children:
                if not lines and label:  # the node starts with a list: its label stands alone
                    lines.append(f"{indent}{label}".rstrip())
                lines.append(self.render(self.nodes[value], depth + 1))
        return "\n".join(line for line in lines if line.strip())

    def refs(self, node: dict) -> list[str]:
        own = {f"art{m}" for m in re.findall(r"_art(\d+[a-z]?)", node["id"])}
        found = []
        for prefix, pattern in REF_PATTERNS.items():
            for match in pattern.finditer(node["text"]):
                if OTHER_ACT.match(node["text"][match.end() : match.end() + 80]):
                    continue
                value = match.group(1)
                ref = f"annex{roman_to_int(value.upper())}" if prefix == "annex" else f"art{value}"
                if ref not in own and ref not in found:
                    found.append(ref)
        return found

    def chunk(self, node: dict) -> Chunk:
        header = self.header(node)
        lead = self.lead_in(node)
        article = re.search(r"_art(\d+[a-z]?)", node["id"])
        paragraph = re.search(r"_art\d+[a-z]?_p([0-9a-z]+)", node["id"])
        return Chunk(
            id=node["id"],
            lang=self.lang,
            kind=node["kind"],
            header=header,
            text=node["text"],
            embed_text="\n".join(part for part in (header, lead, node["text"]) if part),
            context_id=self.context_of(node)["id"],
            article=article.group(1) if article else "",
            paragraph=paragraph.group(1) if paragraph else "",
            annex=node["annex"],
            chapter=node["chapter"],
            refs=self.refs(node),
            binding=node["kind"] != "recital",
            amended=node["amended"],
            source=node["source"],
        )

    def build(self) -> tuple[list[Chunk], list[Context]]:
        chunks = [self.chunk(n) for n in self.nodes.values() if n["text"]]
        context_ids = dict.fromkeys(c.context_id for c in chunks)  # ordered, unique
        # An article, annex or annex section is its own context only through its intro text
        # (e.g. "For the purposes of this Regulation, the following definitions apply:"):
        # its points have their own, smaller contexts.
        contexts = [
            Context(
                id=cid,
                lang=self.lang,
                header=self.header(self.nodes[cid]),
                text=self.render(
                    self.nodes[cid],
                    with_children=self.nodes[cid]["kind"]
                    not in ("article", "annex", "annex_section"),
                ),
                source=self.nodes[cid]["source"],
            )
            for cid in context_ids
        ]
        return chunks, contexts


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(rows: list, path: Path) -> None:
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def latest_processed(processed_dir: Path = PROCESSED_DIR) -> Path:
    versions = sorted(p for p in processed_dir.glob("02024R1689-*") if p.is_dir())
    if not versions:
        raise SystemExit("no parsed nodes in data/processed: run `python -m ingestion.parse` first")
    return versions[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build search chunks and context units.")
    parser.add_argument("--lang", nargs="+", default=["en", "it"], choices=["en", "it"])
    args = parser.parse_args()

    folder = latest_processed()
    for lang in args.lang:
        chunks, contexts = Chunker(read_jsonl(folder / f"{lang}.jsonl"), lang).build()
        write_jsonl(chunks, folder / f"chunks_{lang}.jsonl")
        write_jsonl(contexts, folder / f"contexts_{lang}.jsonl")
        print(f"{lang}: {len(chunks)} chunks, {len(contexts)} context units -> {folder}")


if __name__ == "__main__":
    main()
