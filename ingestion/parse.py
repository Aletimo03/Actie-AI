"""Parse stage: consolidated AI Act HTML -> a flat list of legal nodes.

The consolidated text marks every article as <div class="eli-subdivision"
id="art_N">. Inside it, numbered paragraphs are <div class="norm"> starting
with <span class="no-parag">, and points are "grid-list" rows: the label
("(a)", "(1)") in the first column, the text and any sub-points in the
second. A paragraph's points are sometimes siblings of the paragraph rather
than children, so blocks are read in document order and attach to the most
recent paragraph.

Annexes (<div id="anx_III">) mix four layouts: grid-list points, plain
numbered paragraphs ("3.1. ..."), headings ("Section A", "1. Introduction")
and tables. Headings become annex_section nodes; lettered points that follow
a plain numbered paragraph belong to it (Annex VII 3.1 (a)-(f)).

Recitals exist only in the original 2024 text (consolidations omit them):
<div id="rct_58"> holds a two-cell table, the number and the text.

<p class="modref"> markers show amendments: "▼M1" starts text changed by
the first amending act, "▼B" returns to the basic 2024 text. Nodes inside
an amended stretch get amended=True; the markers never reach the text.
"""

import argparse
import json
import re
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

# The files are XHTML; the lxml HTML parser reads them fine and is lenient.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
BASE_CELEX = "32024R1689"

DELETED = re.compile(r"^[—–-]{3,}$")  # "—————" stands for text repealed by an amendment

# Italian numbers inserted provisions "14 bis", "b ter"; English uses "14a", "bb".
# Mapping the Latin suffixes to letters gives both languages the same ids.
LATIN_SUFFIXES = ["bis", "ter", "quater", "quinquies", "sexies", "septies", "octies", "novies"]
LATIN = re.compile(r"\s*\b(" + "|".join(LATIN_SUFFIXES) + r")\b")

# Annex headings: "Section A.", "Sezione 1", "1. Introduction", "a. AI systems subject to ..."
ANNEX_HEADING = re.compile(
    r"^(?:(?:Section|Sezione)\s+([0-9]+|[A-Z])\.?|([0-9]+|[A-Za-z])[.)])(?:\s+(.+))?$", re.S
)
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", re.S)  # "3.1. The application ..."
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


@dataclass
class Node:
    id: str  # e.g. "en_art6_p3_a": language, article, paragraph, point
    kind: str  # "article" | "paragraph" | "point" | "annex" | "annex_section"
    label: str  # as printed: "Article 6", "3", "(a)"
    text: str  # the node's own words, without its children
    parent_id: str | None
    path: list[str]  # human-readable location, used for chunk headers
    title: str = ""  # article title, e.g. "Classification rules for high-risk AI systems"
    chapter: str = ""  # roman numeral, e.g. "III"
    section: str = ""  # e.g. "1", empty when the chapter has no sections
    annex: str = ""  # roman numeral for annex nodes, e.g. "III"
    source: str = ""  # CELEX of the document the text comes from
    amended: bool = False
    # Reading order of the node's own text and its children: ["t", "text"] or ["c", child id].
    # Needed because text can follow a list ("Notwithstanding the first subparagraph ...").
    parts: list[list[str]] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list, repr=False)


def clean(text: str) -> str:
    """Collapse whitespace, including non-breaking spaces, into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def classes(tag: Tag) -> set[str]:
    return set(tag.get("class") or [])


def roman_to_int(roman: str) -> int:
    values = [ROMAN[c] for c in roman]
    return sum(-v if v < nxt else v for v, nxt in zip(values, values[1:] + [0], strict=True))


def label_key(label: str) -> str:
    """'(a)' -> 'a', '3.' -> '3', '(14a)' and '14 bis)' -> '14a': the part used in ids."""
    label = LATIN.sub(lambda m: "abcdefgh"[LATIN_SUFFIXES.index(m.group(1))], label.lower())
    return re.sub(r"[^0-9a-z]", "", label)


class ArticleParser:
    def __init__(self, lang: str):
        self.lang = lang
        self.amended = False  # carried across the whole document, in reading order
        self.nodes: list[Node] = []
        # Text after a list starts a new subparagraph; its points get "_s2", "_s3"
        # so that e.g. the two (a)-(d) lists of Article 43(1) keep distinct ids.
        self.subparagraph: dict[str, int] = {}

    # -- helpers ---------------------------------------------------------

    def add(self, node: Node, parent: Node | None) -> Node:
        if node.text and not node.parts:  # text given at creation, e.g. "3.1. The application ..."
            node.parts.append(["t", node.text])
        if parent is not None:
            parent.children.append(node)
            parent.parts.append(["c", node.id])
        self.nodes.append(node)
        return node

    def marker(self, tag: Tag) -> bool:
        """Update the amendment state if tag is a ▼ marker; True if it was one."""
        if tag.name == "p" and "modref" in classes(tag):
            self.amended = clean(tag.get_text()).startswith("▼M")
            return True
        return False

    def append_text(self, node: Node, text: str) -> None:
        text = clean(text)
        if text and not DELETED.match(text):
            node.text = f"{node.text}\n{text}" if node.text else text
            node.parts.append(["t", text])
            if node.children:
                self.subparagraph[node.id] = self.subparagraph.get(node.id, 1) + 1

    # -- structure -------------------------------------------------------

    def parse_article(self, div: Tag) -> Node:
        number = div["id"].removeprefix("art_")
        chapter, section = self.location(div)
        heading = div.find("p", class_="title-article-norm", recursive=False)
        title_div = div.find("div", class_="eli-title", recursive=False)
        label = clean(heading.get_text()) if heading else f"Article {number}"
        path = [f"Chapter {chapter}"] + ([f"Section {section}"] if section else []) + [label]
        article = self.add(
            Node(
                id=f"{self.lang}_art{number}",
                kind="article",
                label=label,
                text="",
                parent_id=None,
                path=path,
                title=clean(title_div.get_text()) if title_div else "",
                chapter=chapter,
                section=section,
                amended=self.amended,
            ),
            None,
        )
        current = article  # where loose text and points attach
        for block in div.find_all(recursive=False):
            if block in (heading, title_div) or self.marker(block):
                continue
            number_span = block.find("span", class_="no-parag", recursive=False)
            if block.name == "div" and number_span is not None:
                current = self.parse_paragraph(block, number_span, article)
            else:
                self.parse_block(block, current, article)
        return article

    def parse_paragraph(self, div: Tag, number_span: Tag, article: Node) -> Node:
        label = clean(number_span.get_text()).rstrip(".")
        paragraph = self.add(
            Node(
                id=f"{article.id}_p{label_key(label)}",
                kind="paragraph",
                label=label,
                text="",
                parent_id=article.id,
                path=article.path + [label],
                title=article.title,
                chapter=article.chapter,
                section=article.section,
                amended=self.amended,
            ),
            article,
        )
        for block in div.find_all(recursive=False):
            if block is not number_span:
                self.parse_block(block, paragraph, article)
        return paragraph

    def parse_block(self, block: Tag, owner: Node, article: Node) -> None:
        """A block inside an article or paragraph: text, a point, a wrapper or a marker."""
        if self.marker(block):
            return
        if "grid-list" in classes(block):
            self.parse_point(block, owner, article)
        elif block.name == "div":  # e.g. <div class="norm inline-element"> wrappers
            for child in block.children:  # tags and bare text, in order
                if isinstance(child, Tag):
                    self.parse_block(child, owner, article)
                else:
                    self.append_text(owner, str(child))
        else:
            self.append_text(owner, block.get_text(" "))

    def parse_point(self, grid: Tag, owner: Node, article: Node) -> Node | None:
        label_col = grid.find("div", class_="grid-list-column-1", recursive=False)
        body_col = grid.find("div", class_="grid-list-column-2", recursive=False)
        if label_col is None or body_col is None:
            self.append_text(owner, grid.get_text(" "))
            return None
        label = clean(label_col.get_text()).rstrip(".")  # "4." -> "4", like paragraphs
        # Dash bullets ("—") have no number of their own: use their position.
        key = label_key(label) or str(sum(c.kind == "point" for c in owner.children) + 1)
        sub = self.subparagraph.get(owner.id, 1)
        prefix = f"{owner.id}_s{sub}" if sub > 1 else owner.id
        point = Node(
            id=f"{prefix}_{key}",
            kind="point",
            label=label,
            text="",
            parent_id=owner.id,
            path=owner.path + [label],
            title=article.title,
            chapter=article.chapter,
            section=article.section,
            annex=article.annex,
            amended=self.amended,
        )
        if DELETED.match(clean(body_col.get_text())):
            return None  # repealed point: keep no empty node
        self.add(point, owner)
        for child in body_col.find_all(recursive=False):
            self.parse_block(child, point, article)
        return point

    def parse_annex(self, div: Tag) -> Node:
        roman = div["id"].removeprefix("anx_")
        titles = [
            clean(p.get_text())
            for p in div.find_all("p", class_=["title-annex-1", "title-annex-2"], recursive=False)
        ]
        word, _, number = (titles[0] if titles else f"Annex {roman}").partition(" ")
        label = f"{word.capitalize()} {number}"  # "ANNEX III" -> "Annex III"
        annex = self.add(
            Node(
                id=f"{self.lang}_annex{roman_to_int(roman)}",
                kind="annex",
                label=label,
                text="",
                parent_id=None,
                path=[label],
                title=" ".join(titles[1:]),
                annex=roman,
                amended=self.amended,
            ),
            None,
        )
        sections: list[Node] = []  # open headings, one per level
        numbered: Node | None = None  # last plain "3.1." paragraph in the current section
        for block in div.find_all(recursive=False):
            if self.marker(block) or {"title-annex-1", "title-annex-2"} & classes(block):
                continue
            owner = sections[-1] if sections else annex
            level = next((c for c in classes(block) if c.startswith("title-gr-seq-level-")), None)
            if level:
                depth = int(level.rsplit("-", 1)[1])
                text = clean(block.get_text())
                match = ANNEX_HEADING.match(text)
                if match is None and sections and not sections[-1].title:
                    sections[-1].title = text  # "Section 1" followed by its title line
                elif match is None:
                    self.append_text(owner, text)
                else:
                    del sections[depth - 1 :]
                    parent = sections[-1] if sections else annex
                    sections.append(self.annex_section(match, parent, annex))
                    numbered = None
            elif "grid-list" in classes(block):
                label = clean(block.get_text(" "))
                if numbered is not None and not label[:1].isdigit():
                    owner = numbered  # (a), (b) under a plain "3.1." paragraph
                self.parse_point(block, owner, annex)
            elif block.name == "div" and not classes(block):
                match = NUMBERED.match(clean(block.get_text(" ")))
                if match:
                    numbered = self.annex_numbered(match, owner, annex)
                else:
                    self.append_text(numbered or owner, block.get_text(" "))
            else:  # notes, "p.list" continuations, tables
                self.append_text(numbered or owner, block.get_text(" "))
        return annex

    def annex_section(self, match: re.Match, parent: Node, annex: Node) -> Node:
        number = match.group(1) or match.group(2)
        label = f"Section {number}" if match.group(1) else number
        return self.add(
            Node(
                id=f"{parent.id}_sec{number.lower()}",
                kind="annex_section",
                label=label,
                text="",
                parent_id=parent.id,
                path=parent.path + [label],
                title=(match.group(3) or "").lstrip("—–- "),  # "Section A — Information ..."
                annex=annex.annex,
                amended=self.amended,
            ),
            parent,
        )

    def annex_numbered(self, match: re.Match, owner: Node, annex: Node) -> Node:
        label = match.group(1)
        return self.add(
            Node(
                id=f"{owner.id}_{label.replace('.', '_')}",
                kind="point",
                label=label,
                text=match.group(2),
                parent_id=owner.id,
                path=owner.path + [label],
                annex=annex.annex,
                amended=self.amended,
            ),
            owner,
        )

    @staticmethod
    def location(div: Tag) -> tuple[str, str]:
        """Chapter and section from the enclosing ids, e.g. 'cpt_III.sct_1' -> ('III', '1')."""
        for parent in div.parents:
            match = re.fullmatch(r"cpt_([IVXLC]+)(?:\.sct_(\d+))?", parent.get("id") or "")
            if match:
                return match.group(1), match.group(2) or ""
        return "", ""


def parse_articles(html: str, lang: str) -> list[Node]:
    """All article, paragraph and point nodes of a consolidated text, in reading order."""
    soup = BeautifulSoup(html, "lxml")
    parser = ArticleParser(lang)
    for div in soup.find_all("div", class_="eli-subdivision", id=re.compile(r"^art_\d+[a-z]?$")):
        parser.parse_article(div)
    return parser.nodes


def parse_annexes(html: str, lang: str) -> list[Node]:
    """All annex, annex_section and point nodes, in reading order."""
    soup = BeautifulSoup(html, "lxml")
    parser = ArticleParser(lang)
    for div in soup.find_all("div", id=re.compile(r"^anx_[IVXLC]+$")):
        parser.parse_annex(div)
    return parser.nodes


RECITAL_WORD = {"en": "Recital", "it": "Considerando"}


def parse_recitals(html: str, lang: str) -> list[Node]:
    """One node per recital of the original text. Recitals explain; they do not bind."""
    soup = BeautifulSoup(html, "lxml")
    nodes = []
    for div in soup.find_all("div", class_="eli-subdivision", id=re.compile(r"^rct_\d+$")):
        for note in div.select("a[id^=ntc]"):  # footnote markers: <a>(<span>5</span>)</a>
            note.decompose()
        cells = div.find_all("td")
        number = div["id"].removeprefix("rct_")
        label = f"{RECITAL_WORD[lang]} {number}"
        nodes.append(
            Node(
                id=f"{lang}_rec{number}",
                kind="recital",
                label=label,
                text=clean(cells[-1].get_text(" ")) if cells else clean(div.get_text(" ")),
                parent_id=None,
                path=[label],
            )
        )
    return nodes


def parse_file(path: Path, lang: str) -> list[Node]:
    html = path.read_text(encoding="utf-8")
    return parse_articles(html, lang) + parse_annexes(html, lang)


def latest_consolidated(raw_dir: Path = RAW_DIR) -> str:
    versions = sorted(p.name for p in raw_dir.glob("02024R1689-*") if p.is_dir())
    if not versions:
        raise SystemExit("no consolidated text in data/raw: run `python -m ingestion.fetch` first")
    return versions[-1]  # the date suffix sorts chronologically


def parse_language(lang: str, consolidated: str, raw_dir: Path = RAW_DIR) -> list[Node]:
    """Articles and annexes from the consolidated text, recitals from the original."""
    current = parse_file(raw_dir / consolidated / f"{lang}.html", lang)
    original = raw_dir / BASE_CELEX / f"{lang}.html"
    recitals = parse_recitals(original.read_text(encoding="utf-8"), lang)
    for node in current:
        node.source = consolidated
    for node in recitals:
        node.source = BASE_CELEX
    return current + recitals


def write_jsonl(nodes: list[Node], path: Path) -> None:
    """One node per line, without the in-memory children list (parent_id links them)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for node in nodes:
            row = asdict(node)
            del row["children"]
            out.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse the fetched AI Act into jsonl nodes.")
    parser.add_argument("--lang", nargs="+", default=["en", "it"], choices=["en", "it"])
    args = parser.parse_args()

    consolidated = latest_consolidated()
    for lang in args.lang:
        nodes = parse_language(lang, consolidated)
        path = PROCESSED_DIR / consolidated / f"{lang}.jsonl"
        write_jsonl(nodes, path)
        counts = {}
        for node in nodes:
            counts[node.kind] = counts.get(node.kind, 0) + 1
        print(f"{lang}: {len(nodes)} nodes {counts} -> {path}")


if __name__ == "__main__":
    main()
