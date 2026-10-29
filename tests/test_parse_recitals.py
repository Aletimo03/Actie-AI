import json
from pathlib import Path

import pytest

from ingestion.parse import latest_consolidated, parse_language, parse_recitals, write_jsonl

RECITALS = """
<div class="eli-subdivision" id="rct_8"><table><tbody><tr>
  <td><p class="oj-normal">(8)</p></td>
  <td><p class="oj-normal">The New Legislative Framework
    <a id="ntc5-L_202401689EN"><span class="oj-super oj-note-tag">5</span></a>
    applies.</p></td>
</tr></tbody></table></div>
"""

ARTICLE = """
<div id="cpt_I"><div class="eli-subdivision" id="art_1">
  <p class="title-article-norm">Article 1</p>
  <div class="eli-title"><p>Subject matter</p></div>
  <p class="norm">The purpose of this Regulation is to improve the internal market.</p>
</div></div>
"""


def test_recital_text_without_number_or_footnote_marker():
    [recital] = parse_recitals(RECITALS, "en")
    assert (recital.id, recital.kind, recital.label) == ("en_rec8", "recital", "Recital 8")
    assert recital.text == "The New Legislative Framework applies."


def test_italian_recital_label():
    [recital] = parse_recitals(RECITALS, "it")
    assert (recital.id, recital.label) == ("it_rec8", "Considerando 8")


@pytest.fixture
def raw_dir(tmp_path):
    for celex, html in (("02024R1689-20240712", ""), ("02024R1689-20260727", ARTICLE)):
        (tmp_path / celex).mkdir()
        (tmp_path / celex / "en.html").write_text(html, encoding="utf-8")
    (tmp_path / "32024R1689").mkdir()
    (tmp_path / "32024R1689" / "en.html").write_text(RECITALS, encoding="utf-8")
    return tmp_path


def test_newest_consolidated_version_is_used(raw_dir):
    assert latest_consolidated(raw_dir) == "02024R1689-20260727"


def test_language_combines_both_documents_and_records_the_source(raw_dir, tmp_path):
    nodes = parse_language("en", "02024R1689-20260727", raw_dir)
    sources = {n.id: n.source for n in nodes}
    assert sources == {"en_art1": "02024R1689-20260727", "en_rec8": "32024R1689"}

    out = tmp_path / "out" / "en.jsonl"
    write_jsonl(nodes, out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["en_art1", "en_rec8"]
    assert "children" not in rows[0]


RAW = Path("data/raw/32024R1689")


@pytest.mark.skipif(not RAW.exists(), reason="run `python -m ingestion.fetch` first")
def test_real_recitals():
    for lang in ("en", "it"):
        recitals = parse_recitals((RAW / f"{lang}.html").read_text(encoding="utf-8"), lang)
        assert [r.id for r in recitals] == [f"{lang}_rec{n}" for n in range(1, 181)]
        assert all(r.text and "()" not in r.text for r in recitals)
