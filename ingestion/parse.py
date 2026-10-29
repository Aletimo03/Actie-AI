"""Parse stage: consolidated AI Act HTML -> a flat list of legal nodes.

The consolidated text marks every article as <div class="eli-subdivision"
id="art_N">. Inside it, numbered paragraphs are <div class="norm"> starting
with <span class="no-parag">, and points are "grid-list" rows: the label
("(a)", "(1)") in the first column, the text and any sub-points in the
second. A paragraph's points are sometimes siblings of the paragraph rather
than children, so blocks are read in document order and attach to the most
recent paragraph.

<p class="modref"> markers show amendments: "▼M1" starts text changed by
the first amending act, "▼B" returns to the basic 2024 text. Nodes inside
an amended stretch get amended=True; the markers never reach the text.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag

DELETED = re.compile(r"^[—–-]{3,}$")  # "—————" stands for text repealed by an amendment

# Italian numbers inserted provisions "14 bis", "b ter"; English uses "14a", "bb".
# Mapping the Latin suffixes to letters gives both languages the same ids.
LATIN_SUFFIXES = ["bis", "ter", "quater", "quinquies", "sexies", "septies", "octies", "novies"]
LATIN = re.compile(r"\s*\b(" + "|".join(LATIN_SUFFIXES) + r")\b")


@dataclass
class Node:
    id: str  # e.g. "en_art6_p3_a": language, article, paragraph, point
    kind: str  # "article" | "paragraph" | "point"
    label: str  # as printed: "Article 6", "3", "(a)"
    text: str  # the node's own words, without its children
    parent_id: str | None
    path: list[str]  # human-readable location, used for chunk headers
    title: str = ""  # article title, e.g. "Classification rules for high-risk AI systems"
    chapter: str = ""  # roman numeral, e.g. "III"
    section: str = ""  # e.g. "1", empty when the chapter has no sections
    amended: bool = False
    children: list["Node"] = field(default_factory=list, repr=False)


def clean(text: str) -> str:
    """Collapse whitespace, including non-breaking spaces, into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def classes(tag: Tag) -> set[str]:
    return set(tag.get("class") or [])


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
        if parent is not None:
            parent.children.append(node)
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

    def parse_point(self, grid: Tag, owner: Node, article: Node) -> None:
        label_col = grid.find("div", class_="grid-list-column-1", recursive=False)
        body_col = grid.find("div", class_="grid-list-column-2", recursive=False)
        if label_col is None or body_col is None:
            self.append_text(owner, grid.get_text(" "))
            return
        label = clean(label_col.get_text())
        sub = self.subparagraph.get(owner.id, 1)
        prefix = f"{owner.id}_s{sub}" if sub > 1 else owner.id
        point = Node(
            id=f"{prefix}_{label_key(label)}",
            kind="point",
            label=label,
            text="",
            parent_id=owner.id,
            path=owner.path + [label],
            title=article.title,
            chapter=article.chapter,
            section=article.section,
            amended=self.amended,
        )
        if DELETED.match(clean(body_col.get_text())):
            return  # repealed point: keep no empty node
        self.add(point, owner)
        for child in body_col.find_all(recursive=False):
            self.parse_block(child, point, article)

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


def parse_file(path: Path, lang: str) -> list[Node]:
    return parse_articles(path.read_text(encoding="utf-8"), lang)
