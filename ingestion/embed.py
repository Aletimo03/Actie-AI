"""Embed stage: search chunks -> 1024-d bge-m3 vectors, through a local Ollama.

Vectors are cached in data/processed/<version>/embeddings_<lang>.jsonl, keyed
by content_hash = sha256(model + embed_text). A chunk whose text and model are
unchanged reuses its cached vector, so re-running on the same law makes no
model calls; only new or edited chunks are embedded.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from ingestion.chunk import latest_processed, read_jsonl

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "bge-m3")
BATCH_SIZE = 32  # measured: 16, 32 and 64 all give ~24 chunks/s on an M-series Mac


def content_hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def normalize(vector: list[float]) -> list[float]:
    """Scale to length 1, so cosine distance and dot product rank results the same way."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


class OllamaEmbedder:
    def __init__(self, client: httpx.Client, url: str = OLLAMA_URL, model: str = EMBEDDING_MODEL):
        self.client = client
        self.url = url.rstrip("/")
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One call to Ollama's /api/embed for a batch of texts."""
        try:
            response = self.client.post(
                f"{self.url}/api/embed", json={"model": self.model, "input": texts}
            )
        except httpx.ConnectError as error:
            raise SystemExit(f"cannot reach Ollama at {self.url}: is it running?") from error
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        if len(vectors) != len(texts):
            raise RuntimeError(f"asked for {len(texts)} embeddings, got {len(vectors)}")
        return [normalize(v) for v in vectors]


def embed_chunks(
    chunks: list[dict],
    embed: Callable[[list[str]], list[list[float]]],
    model: str,
    cache: dict[str, list[float]],
    batch_size: int = BATCH_SIZE,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> tuple[dict[str, list[float]], int]:
    """Vectors for every chunk, by content hash; returns them and how many were new."""
    hashes = [content_hash(model, c["embed_text"]) for c in chunks]
    todo = {h: c["embed_text"] for h, c in zip(hashes, chunks, strict=True) if h not in cache}
    pending = list(todo.items())
    vectors = {h: cache[h] for h in hashes if h in cache}
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        for (h, _), vector in zip(batch, embed([text for _, text in batch]), strict=True):
            vectors[h] = vector
        progress(min(start + batch_size, len(pending)), len(pending))
    return vectors, len(pending)


def read_cache(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    return {row["hash"]: row["vector"] for row in read_jsonl(path)}


def write_cache(vectors: dict[str, list[float]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as out:
        for h, vector in vectors.items():
            out.write(json.dumps({"hash": h, "vector": [round(x, 7) for x in vector]}) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed search chunks with bge-m3 via Ollama.")
    parser.add_argument("--lang", nargs="+", default=["en", "it"], choices=["en", "it"])
    args = parser.parse_args()

    folder = latest_processed()
    with httpx.Client(timeout=300) as client:
        embedder = OllamaEmbedder(client)
        for lang in args.lang:
            chunks = read_jsonl(folder / f"chunks_{lang}.jsonl")
            cache_path = folder / f"embeddings_{lang}.jsonl"
            started = time.monotonic()

            def progress(done: int, total: int, lang: str = lang) -> None:
                print(f"\r{lang}: embedded {done}/{total}", end="", file=sys.stderr, flush=True)

            vectors, new = embed_chunks(
                chunks, embedder.embed, embedder.model, read_cache(cache_path), progress=progress
            )
            write_cache(vectors, cache_path)
            seconds = time.monotonic() - started
            print(
                f"\r{lang}: {len(chunks)} chunks, {new} embedded, {len(chunks) - new} from cache "
                f"in {seconds:.0f}s -> {cache_path}"
            )


if __name__ == "__main__":
    main()
