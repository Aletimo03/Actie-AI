import json

import httpx

from ingestion.fetch import fetch_document, latest_consolidated_celex, sha256_of


def make_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sha256_of_known_value():
    assert sha256_of(b"abc").startswith("ba7816bf")


def test_latest_consolidated_picks_newest_date():
    def handler(request):
        rows = ["02024R1689-20240712", "02024R1689-20260727"]
        body = {"results": {"bindings": [{"celex": {"value": c}} for c in rows]}}
        return httpx.Response(200, json=body)

    assert latest_consolidated_celex(make_client(handler)) == "02024R1689-20260727"


def test_fetch_saves_html_and_metadata(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.headers["Accept-Language"])
        return httpx.Response(200, content=b"<html>Article 5</html>")

    result = fetch_document(make_client(handler), "32024R1689", "it", raw_dir=tmp_path)

    assert seen == ["ita"]
    assert (tmp_path / "32024R1689" / "it.html").read_bytes() == b"<html>Article 5</html>"
    meta = json.loads((tmp_path / "32024R1689" / "it.json").read_text())
    assert meta["sha256"] == result.sha256 == sha256_of(b"<html>Article 5</html>")


def test_fetch_skips_existing_unless_forced(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=b"v1")

    client = make_client(handler)
    fetch_document(client, "32024R1689", "en", raw_dir=tmp_path)
    fetch_document(client, "32024R1689", "en", raw_dir=tmp_path)
    assert len(calls) == 1
    fetch_document(client, "32024R1689", "en", raw_dir=tmp_path, force=True)
    assert len(calls) == 2
