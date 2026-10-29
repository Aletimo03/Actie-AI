import json
import math

import httpx
import pytest

from ingestion.embed import (
    OllamaEmbedder,
    content_hash,
    embed_chunks,
    normalize,
    read_cache,
    write_cache,
)


def test_normalize_gives_unit_length():
    assert normalize([3.0, 4.0]) == [0.6, 0.8]
    assert normalize([0.0, 0.0]) == [0.0, 0.0]


def test_hash_changes_with_text_and_model():
    base = content_hash("bge-m3", "Article 6")
    assert base == content_hash("bge-m3", "Article 6")
    assert base != content_hash("bge-m3", "Article 7")
    assert base != content_hash("other-model", "Article 6")


def fake_embed(calls):
    def embed(texts):
        calls.append(len(texts))
        return [normalize([float(len(t)), 1.0]) for t in texts]

    return embed


def chunks(*texts):
    return [{"embed_text": t} for t in texts]


def test_batches_and_progress():
    calls, seen = [], []
    vectors, new = embed_chunks(
        chunks("a", "bb", "ccc", "dddd", "eeeee"),
        fake_embed(calls),
        "m",
        cache={},
        batch_size=2,
        progress=lambda done, total: seen.append((done, total)),
    )
    assert (len(vectors), new, calls) == (5, 5, [2, 2, 1])
    assert seen == [(2, 5), (4, 5), (5, 5)]


def test_cached_chunks_are_not_embedded_again():
    calls = []
    cache = {content_hash("m", "a"): [1.0, 0.0]}
    vectors, new = embed_chunks(chunks("a", "bb"), fake_embed(calls), "m", cache=cache)
    assert (new, calls) == (1, [1])
    assert vectors[content_hash("m", "a")] == [1.0, 0.0]


def test_identical_texts_are_embedded_once():
    calls = []
    _, new = embed_chunks(chunks("same", "same"), fake_embed(calls), "m", cache={})
    assert (new, calls) == (1, [1])


def test_cache_file_round_trip(tmp_path):
    path = tmp_path / "embeddings_en.jsonl"
    write_cache({"h1": [0.6, 0.8]}, path)
    assert read_cache(path) == {"h1": [0.6, 0.8]}
    assert read_cache(tmp_path / "missing.jsonl") == {}


def test_ollama_request_and_normalized_answer():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/embed"
        assert body == {"model": "bge-m3", "input": ["x", "y"]}
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0], [0.0, 2.0]]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    vectors = OllamaEmbedder(client, url="http://ollama", model="bge-m3").embed(["x", "y"])
    assert vectors == [[0.6, 0.8], [0.0, 1.0]]
    assert all(math.isclose(math.hypot(*v), 1.0) for v in vectors)


def test_clear_error_when_ollama_is_down():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SystemExit, match="is it running"):
        OllamaEmbedder(client, url="http://ollama").embed(["x"])
