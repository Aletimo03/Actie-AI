from dataclasses import asdict

import pytest

from ingestion.chunk import Chunker
from ingestion.parse import parse_annexes, parse_articles, parse_recitals

ARTICLES = """
<div id="cpt_I"><div class="eli-subdivision" id="art_3">
  <p class="title-article-norm">Article 3</p>
  <div class="eli-title"><p>Definitions</p></div>
  <p class="norm">For the purposes of this Regulation, the following definitions apply:</p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(1) </span></div>
    <div class="grid-list-column-2"><p class="norm">'AI system' means a system;</p></div>
  </div>
</div></div>
<div id="cpt_III"><div id="cpt_III.sct_1"><div class="eli-subdivision" id="art_6">
  <p class="title-article-norm">Article 6</p>
  <div class="eli-title"><p>Classification rules</p></div>
  <div class="norm"><span class="no-parag">3. </span>
    <div class="norm inline-element">By derogation from paragraph 2, a system in Annex III is not
    high-risk, as provided in Article 9 of Regulation (EU) 2016/679.</div>
  </div>
  <p class="norm">The first subparagraph applies where:</p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(a) </span></div>
    <div class="grid-list-column-2"><p class="norm">a narrow procedural task;</p></div>
  </div>
  <p class="norm">Profiling is always high-risk.</p>
</div></div></div>
"""

ANNEX = """
<div id="anx_II">
  <p class="title-annex-1">ANNEX II</p>
  <p class="title-annex-2">List of criminal offences</p>
  <p class="norm">Criminal offences referred to in Article 5:</p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>— </span></div>
    <div class="grid-list-column-2"><p class="norm">terrorism,</p></div>
  </div>
</div>
"""

RECITAL = """
<div class="eli-subdivision" id="rct_58"><table><tr>
  <td><p>(58)</p></td><td><p>Access to essential services deserves attention.</p></td>
</tr></table></div>
"""


def build(lang="en"):
    nodes = (
        parse_articles(ARTICLES, lang) + parse_annexes(ANNEX, lang) + parse_recitals(RECITAL, lang)
    )
    rows = []
    for node in nodes:
        row = asdict(node)
        del row["children"]
        rows.append(row)
    chunks, contexts = Chunker(rows, lang).build()
    return {c.id: c for c in chunks}, {c.id: c for c in contexts}


@pytest.fixture
def built():
    return build()


def test_header_names_the_full_location(built):
    chunks, _ = built
    assert chunks["en_art6_p3_a"].header == (
        "AI Act › Chapter III › Section 1 › Article 6 Classification rules › 3 › (a)"
    )


def test_point_lead_in_is_the_text_right_before_its_list(built):
    chunks, _ = built
    assert chunks["en_art6_p3_a"].embed_text.splitlines()[1:] == [
        "The first subparagraph applies where:",
        "a narrow procedural task;",
    ]
    assert chunks["en_annex2_1"].embed_text.endswith(
        "Criminal offences referred to in Article 5:\nterrorism,"
    )


def test_context_is_the_paragraph_in_reading_order(built):
    chunks, contexts = built
    assert chunks["en_art6_p3_a"].context_id == "en_art6_p3"
    lines = contexts["en_art6_p3"].text.splitlines()
    assert lines[2] == "  (a) a narrow procedural task;"
    assert lines[3] == "Profiling is always high-risk."  # after the list, as in the law


def test_article_without_paragraphs_uses_top_level_points(built):
    chunks, contexts = built
    assert chunks["en_art3_1"].context_id == "en_art3_1"
    # The article's own intro is a small context, not all its definitions.
    assert (
        contexts["en_art3"].text
        == "For the purposes of this Regulation, the following definitions apply:"
    )


def test_refs_keep_this_act_and_skip_other_acts(built):
    chunks, _ = built
    assert chunks["en_art6_p3"].refs == ["annex3"]  # not "art9" of Regulation 2016/679
    assert chunks["en_annex2"].refs == ["art5"]


def test_filter_fields(built):
    chunks, _ = built
    point = chunks["en_art6_p3_a"]
    assert (point.article, point.paragraph, point.chapter, point.binding) == ("6", "3", "III", True)
    assert chunks["en_annex2_1"].annex == "II"
    assert chunks["en_rec58"].binding is False


def test_italian_headers_use_italian_words():
    chunks, _ = build("it")
    assert chunks["it_art6_p3_a"].header.startswith("Regolamento IA › Capo III › Sezione 1 › ")
