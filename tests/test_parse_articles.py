from pathlib import Path

import pytest

from ingestion.parse import label_key, parse_articles

# A shrunken copy of the consolidated markup, with the cases that broke early versions.
HTML = """
<div id="cpt_III"><div id="cpt_III.sct_1">
<div class="eli-subdivision" id="art_6">
  <p class="title-article-norm">Article 6</p>
  <div class="eli-title"><p>Classification rules for high-risk AI systems</p></div>
  <div class="norm"><span class="no-parag">2. </span>
    <div class="norm inline-element">AI systems referred to in Annex III are high-risk.</div>
  </div>
  <div class="norm"><span class="no-parag">3. </span>
    <div class="norm inline-element">By derogation from paragraph 2, not high-risk where:</div>
  </div>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(a) </span></div>
    <div class="grid-list-column-2"><p class="norm">a narrow procedural task;</p></div>
  </div>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(b) </span></div>
    <div class="grid-list-column-2">
      <p class="norm">a task with sub-points:</p>
      <div class="grid-container grid-list">
        <div class="list grid-list-column-1"><span>(i) </span></div>
        <div class="grid-list-column-2"><p class="norm">first sub-point;</p></div>
      </div>
    </div>
  </div>
  <p class="norm">Profiling is always high-risk.</p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(a) </span></div>
    <div class="grid-list-column-2"><p class="norm">a second list, second subparagraph;</p></div>
  </div>
  <p class="modref"><a>▼M1</a></p>
  <div class="norm"><span class="no-parag">3a. </span>
    <div class="norm inline-element">Inserted by the amendment.</div>
  </div>
  <p class="modref"><a>▼M1</a></p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(c) </span></div>
    <div class="grid-list-column-2"><p class="norm">—————</p></div>
  </div>
  <p class="modref"><a>▼B</a></p>
  <div class="norm"><span class="no-parag">4. </span>
    <div class="norm inline-element">Back to the original text.</div>
  </div>
</div>
</div></div>
"""


@pytest.fixture
def nodes():
    return {n.id: n for n in parse_articles(HTML, "en")}


def test_article_metadata(nodes):
    article = nodes["en_art6"]
    assert article.title == "Classification rules for high-risk AI systems"
    assert (article.chapter, article.section) == ("III", "1")
    assert article.path == ["Chapter III", "Section 1", "Article 6"]


def test_text_directly_inside_wrappers_is_kept(nodes):
    assert nodes["en_art6_p3"].text.startswith("By derogation from paragraph 2")


def test_sibling_points_attach_to_the_last_paragraph(nodes):
    point = nodes["en_art6_p3_a"]
    assert point.parent_id == "en_art6_p3"
    assert point.path == ["Chapter III", "Section 1", "Article 6", "3", "(a)"]


def test_nested_points(nodes):
    assert nodes["en_art6_p3_b_i"].text == "first sub-point;"
    assert nodes["en_art6_p3_b"].text == "a task with sub-points:"


def test_text_after_a_list_stays_with_the_paragraph(nodes):
    assert "Profiling is always high-risk." in nodes["en_art6_p3"].text


def test_second_list_in_a_paragraph_gets_distinct_ids(nodes):
    assert nodes["en_art6_p3_s2_a"].text == "a second list, second subparagraph;"


def test_amendment_markers_set_the_flag_and_never_reach_the_text(nodes):
    assert nodes["en_art6_p3a"].amended
    assert not nodes["en_art6_p4"].amended
    assert not nodes["en_art6_p2"].amended
    assert all("▼" not in n.text for n in nodes.values())


def test_repealed_points_are_skipped(nodes):
    assert "en_art6_p3_s2_c" not in nodes and "en_art6_p3_c" not in nodes


@pytest.mark.parametrize(
    ("label", "key"),
    [
        ("(a)", "a"),
        ("3.", "3"),
        ("(14a)", "14a"),
        ("14 bis)", "14a"),
        ("b ter)", "bb"),
        ("ii)", "ii"),
    ],
)
def test_label_key_matches_across_languages(label, key):
    assert label_key(label) == key


RAW = Path("data/raw/02024R1689-20260727")


@pytest.mark.skipif(not RAW.exists(), reason="run `python -m ingestion.fetch` first")
def test_real_consolidated_text():
    by_lang = {
        lang: parse_articles((RAW / f"{lang}.html").read_text(encoding="utf-8"), lang)
        for lang in ("en", "it")
    }
    for nodes in by_lang.values():
        ids = [n.id for n in nodes]
        assert sum(n.kind == "article" for n in nodes) == 119  # 113 + 6 added in 2026
        assert len(ids) == len(set(ids))
        assert all(n.text or n.children for n in nodes)
    en, it = ({n.id[3:] for n in nodes} for nodes in by_lang.values())
    assert en == it  # every English node has its Italian twin
    text = {n.id: n.text for n in by_lang["en"]}
    assert "emotions" in text["en_art5_p1_f"]
    assert "narrow procedural task" in text["en_art6_p3_a"]
