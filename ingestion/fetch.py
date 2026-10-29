"""Fetch stage: download the AI Act from the EU Publications Office.

EUR-Lex web pages sit behind a JavaScript bot check, so we use the
Publications Office's machine endpoint instead: the same documents,
served by content negotiation on the CELEX number.

Each download is saved under data/raw/<celex>/<lang>.html with a
<lang>.json metadata file (source URL, fetch time, SHA-256). Files
already on disk are not downloaded again unless force=True.
"""

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE_CELEX = "32024R1689"  # Regulation (EU) 2024/1689, as published in 2024
RESOURCE_URL = "https://publications.europa.eu/resource/celex/{celex}"
SPARQL_URL = "https://publications.europa.eu/webapi/rdf/sparql"
LANGUAGES = {"en": "eng", "it": "ita"}  # our code -> Publications Office code
RAW_DIR = Path("data/raw")

# Consolidated versions have CELEX numbers like 02024R1689-20260727,
# one per date on which amendments took effect.
CONSOLIDATED_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?celex WHERE {
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(STRSTARTS(STR(?celex), "02024R1689-"))
}
"""


@dataclass
class FetchResult:
    celex: str
    lang: str
    source_url: str
    resolved_url: str
    fetched_at: str
    sha256: str
    size_bytes: int
    path: str


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def latest_consolidated_celex(client: httpx.Client) -> str:
    """Ask the Publications Office which consolidated versions exist; return the newest."""
    response = client.get(
        SPARQL_URL,
        params={"query": CONSOLIDATED_QUERY},
        headers={"Accept": "application/sparql-results+json"},
    )
    response.raise_for_status()
    versions = [b["celex"]["value"] for b in response.json()["results"]["bindings"]]
    if not versions:
        raise RuntimeError("no consolidated version found")
    return max(versions)  # the date suffix sorts chronologically


def fetch_document(
    client: httpx.Client, celex: str, lang: str, raw_dir: Path = RAW_DIR, force: bool = False
) -> FetchResult:
    """Download one CELEX document in one language, unless it is already on disk."""
    out_dir = raw_dir / celex
    html_path = out_dir / f"{lang}.html"
    meta_path = out_dir / f"{lang}.json"
    if html_path.exists() and meta_path.exists() and not force:
        return FetchResult(**json.loads(meta_path.read_text()))

    source_url = RESOURCE_URL.format(celex=celex)
    response = client.get(
        source_url,
        headers={"Accept": "application/xhtml+xml", "Accept-Language": LANGUAGES[lang]},
        follow_redirects=True,
    )
    response.raise_for_status()

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_bytes(response.content)
    result = FetchResult(
        celex=celex,
        lang=lang,
        source_url=source_url,
        resolved_url=str(response.url),
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        sha256=sha256_of(response.content),
        size_bytes=len(response.content),
        path=str(html_path),
    )
    meta_path.write_text(json.dumps(asdict(result), indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the AI Act (consolidated + original).")
    parser.add_argument("--lang", nargs="+", default=list(LANGUAGES), choices=list(LANGUAGES))
    parser.add_argument("--force", action="store_true", help="download again even if on disk")
    args = parser.parse_args()

    with httpx.Client(timeout=60) as client:
        consolidated = latest_consolidated_celex(client)
        print(f"latest consolidated version: {consolidated}")
        # The consolidated text holds the current articles and annexes;
        # the original adds the recitals, which consolidations leave out.
        for celex in (consolidated, BASE_CELEX):
            for lang in args.lang:
                r = fetch_document(client, celex, lang, force=args.force)
                print(f"{r.celex} {r.lang}: {r.size_bytes:>9,} bytes  sha256 {r.sha256[:12]}…")


if __name__ == "__main__":
    main()
