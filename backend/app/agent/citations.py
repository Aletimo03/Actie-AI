"""Last step before the report: check every citation against the law text (Lecture 07).

Code builds each citation's chunk id from the model's label ("4(a)" ->
"en_annex3_4_a"), and the model writes the quote. Both can be wrong: a point
that does not exist, or words that are not in the text. So for each citation:
1. the chunk must exist in the current version;
2. the quote must be in that chunk, after normalising whitespace, quotes,
   dashes and case; a quote that skips words with "..." passes if every
   fragment appears, in order. No fuzzy matching: one changed word
   ("shall" / "shall not") can reverse a provision.
The model reads whole contexts (Article 6(3) with its points), so a correct
quote may sit in a sibling chunk of the same context: the citation then moves
to that chunk. A citation that still fails is kept and marked unverified, and
the verdict stands: like an open exception, it errs towards more obligations.
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

import psycopg

from backend.app.agent.prohibited import Citation
from backend.app.retrieval.scope import CURRENT_VERSION

ELLIPSIS = re.compile(r"\.\.\.|…|\[\.\.\.\]")
QUOTES = str.maketrans(
    {"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"', "«": '"', "»": '"'}
)
DASHES = re.compile(r"[‐‑‒–—―]")
EDGES = " \t\n'\".,;:()[]"


@dataclass
class Chunk:
    id: str
    context_id: str
    text: str


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(QUOTES)
    text = DASHES.sub("-", text)
    return " ".join(text.split()).lower().strip(EDGES)


def quote_in(quote: str, text: str) -> bool:
    """Every fragment of the quote (split at "...") appears in the text, in order."""
    fragments = [f for f in map(normalise, ELLIPSIS.split(quote)) if f]
    if not fragments:
        return False
    haystack, start = normalise(text), 0
    for fragment in fragments:
        found = haystack.find(fragment, start)
        if found < 0:
            return False
        start = found + len(fragment)
    return True


def fetch_chunks(conn: psycopg.Connection, ids: list[str]) -> list[Chunk]:
    """The chunks with these ids and every chunk of their contexts, from the current version.

    Unknown ids are left out, not raised: a missing chunk is what verify reports.
    """
    rows = conn.execute(
        "SELECT id, context_id, text FROM chunks "
        f"WHERE version = {CURRENT_VERSION} AND context_id IN "
        f"(SELECT context_id FROM chunks WHERE version = {CURRENT_VERSION} "
        "AND id = ANY(%(ids)s)) ORDER BY id",
        {"ids": ids},
    ).fetchall()
    return [Chunk(*row) for row in rows]


def verify(citations: list[Citation], lookup: Callable[[list[str]], list[Chunk]]) -> list[Citation]:
    """Each citation checked (verified, note), moved to a sibling chunk if the quote is there."""
    chunks = lookup(sorted({c.chunk_id for c in citations})) if citations else []
    by_id = {chunk.id: chunk for chunk in chunks}
    checked = []
    for citation in citations:
        chunk = by_id.get(citation.chunk_id)
        if chunk is None:
            update = {"verified": False, "note": "not a provision of the current text"}
        elif not citation.quote.strip():
            update = {"verified": False, "note": "no quote given"}
        elif quote_in(citation.quote, chunk.text):
            update = {"verified": True, "note": ""}
        else:
            siblings = [c for c in chunks if c.context_id == chunk.context_id and c is not chunk]
            sibling = next((c for c in siblings if quote_in(citation.quote, c.text)), None)
            if sibling:
                note = f"quote found in {sibling.id}, not {chunk.id}"
                update = {"chunk_id": sibling.id, "verified": True, "note": note}
            else:
                update = {"verified": False, "note": f"quote not found in {chunk.id}"}
        checked.append(citation.model_copy(update=update))
    return checked
