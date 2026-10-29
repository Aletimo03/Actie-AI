"""Re-ranking: a cross-encoder reads the question and each candidate together.

Vector search compares vectors computed separately for the question and the
chunk; a cross-encoder runs the model on the pair, so it can tell who does
what ("companies that use a system" vs provider duties). It costs one model
pass per pair, so it only reorders the top candidates of hybrid search.

Model: BAAI/bge-reranker-v2-m3 (multilingual, Apache-2.0, ~2.3 GB, cached by
Hugging Face in ~/.cache/huggingface). Runs on the Mac GPU (MPS) when present.
"""

import os
from dataclasses import replace
from functools import cached_property

from backend.app.retrieval.vector import Hit

RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
MAX_TOKENS = 512  # longest (question + chunk) the model reads; our chunks average ~120 tokens


class Reranker:
    def __init__(self, model: str = RERANK_MODEL, device: str | None = None):
        self.model_name = model
        self.device = device

    @cached_property
    def model(self):
        """Loaded on first use: importing torch and the weights takes seconds."""
        import torch
        from sentence_transformers import CrossEncoder

        device = self.device or ("mps" if torch.backends.mps.is_available() else "cpu")
        return CrossEncoder(self.model_name, device=device, max_length=MAX_TOKENS)

    def scores(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(query, p) for p in passages])]

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]:
        """The k best hits by cross-encoder score; each hit's score becomes that score."""
        if not hits:
            return []
        # The header tells the model where the text sits: "Article 26 Obligations of deployers".
        scores = self.scores(query, [f"{h.header}\n{h.text}" for h in hits])
        ranked = sorted(zip(scores, hits, strict=True), key=lambda pair: -pair[0])
        return [replace(hit, score=score) for score, hit in ranked[:k]]
