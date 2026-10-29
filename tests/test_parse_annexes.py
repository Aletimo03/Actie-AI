from pathlib import Path

import pytest

from ingestion.parse import parse_annexes, roman_to_int

# One annex per layout found in the consolidated text.
HTML = """
<div id="anx_II">
  <p class="title-annex-1">ANNEX II</p>
  <p class="title-annex-2">List of criminal offences</p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>— </span></div>
    <div class="grid-list-column-2"><p class="norm">terrorism,</p></div>
  </div>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>— </span></div>
    <div class="grid-list-column-2"><p class="norm">trafficking in human beings,</p></div>
  </div>
</div>
<div id="anx_III">
  <p class="title-annex-1">ANNEX III</p>
  <p class="title-annex-2">High-risk AI systems referred to in Article 6(2)</p>
  <p class="norm">High-risk AI systems are the AI systems listed in any of the following areas:</p>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>4. </span></div>
    <div class="grid-list-column-2">
      <p class="norm">Employment:</p>
      <div class="grid-container grid-list">
        <div class="list grid-list-column-1"><span>(a) </span></div>
        <div class="grid-list-column-2"><p class="norm">recruitment or selection;</p></div>
      </div>
    </div>
  </div>
</div>
<div id="anx_VII">
  <p class="title-annex-1">ANNEX VII</p>
  <p class="title-annex-2">Conformity based on a quality management system</p>
  <p class="title-gr-seq-level-1">3. Quality management system</p>
  <div>3.1. The application of the provider shall include:</div>
  <div class="grid-container grid-list">
    <div class="list grid-list-column-1"><span>(a) </span></div>
    <div class="grid-list-column-2"><p class="norm">the name of the provider;</p></div>
  </div>
  <p class="list">The decision shall be notified to the provider.</p>
</div>
<div id="anx_XI">
  <p class="title-annex-1">ANNEX XI</p>
  <p class="title-annex-2">Technical documentation</p>
  <p class="title-gr-seq-level-1">Section 1</p>
  <p class="title-gr-seq-level-1">Information to be provided by all providers</p>
  <div class="centered"><table><tr><td>AIA Code</td><td>AIB 0201</td></tr></table></div>
</div>
"""


@pytest.fixture
def nodes():
    return {n.id: n for n in parse_annexes(HTML, "en")}


def test_annex_node(nodes):
    annex = nodes["en_annex3"]
    assert (annex.label, annex.annex) == ("Annex III", "III")
    assert annex.title == "High-risk AI systems referred to in Article 6(2)"
    assert annex.text.startswith("High-risk AI systems are the AI systems listed")


def test_nested_grid_points(nodes):
    point = nodes["en_annex3_4_a"]
    assert point.text == "recruitment or selection;"
    assert point.path == ["Annex III", "4", "(a)"]
    assert nodes["en_annex3_4"].text == "Employment:"


def test_dash_bullets_are_numbered_by_position(nodes):
    assert nodes["en_annex2_1"].text == "terrorism,"
    assert nodes["en_annex2_2"].text == "trafficking in human beings,"


def test_headings_plain_paragraphs_and_their_points(nodes):
    section = nodes["en_annex7_sec3"]
    assert (section.kind, section.label, section.title) == (
        "annex_section",
        "3",
        "Quality management system",
    )
    paragraph = nodes["en_annex7_sec3_3_1"]
    assert paragraph.text.startswith("The application of the provider")
    assert "The decision shall be notified" in paragraph.text  # continuation line
    assert nodes["en_annex7_sec3_3_1_a"].parent_id == paragraph.id


def test_section_title_on_its_own_line_and_tables(nodes):
    section = nodes["en_annex11_sec1"]
    assert (section.label, section.title) == (
        "Section 1",
        "Information to be provided by all providers",
    )
    assert "AIB 0201" in section.text


@pytest.mark.parametrize(("roman", "number"), [("I", 1), ("IV", 4), ("IX", 9), ("XIV", 14)])
def test_roman_to_int(roman, number):
    assert roman_to_int(roman) == number


RAW = Path("data/raw/02024R1689-20260727")


@pytest.mark.skipif(not RAW.exists(), reason="run `python -m ingestion.fetch` first")
def test_real_annexes():
    by_lang = {
        lang: parse_annexes((RAW / f"{lang}.html").read_text(encoding="utf-8"), lang)
        for lang in ("en", "it")
    }
    for nodes in by_lang.values():
        ids = [n.id for n in nodes]
        assert sum(n.kind == "annex" for n in nodes) == 14  # Annex XIV added in 2026
        assert len(ids) == len(set(ids))
    en, it = ({n.id[3:] for n in nodes} for nodes in by_lang.values())
    assert en == it
    text = {n.id: n.text for n in by_lang["en"]}
    assert "recruitment or selection" in text["en_annex3_4_a"]
    assert "creditworthiness" in text["en_annex3_5_b"]
