from backend.app.retrieval.rerank import Reranker
from backend.app.retrieval.vector import Hit


class FakeReranker(Reranker):
    """Scores by a lookup table instead of the 2.3 GB model; records what it was asked."""

    def __init__(self, table):
        super().__init__()
        self.table, self.seen = table, []

    def scores(self, query, passages):
        self.seen += passages
        return [self.table[p.split("\n")[1]] for p in passages]


def hit(i, text):
    return Hit(i, 0.0, f"AI Act › Article {i}", text, i)


def test_hits_are_reordered_by_cross_encoder_score_and_cut_to_k():
    reranker = FakeReranker({"provider duties": 0.2, "deployer duties": 0.9, "recital": 0.5})
    hits = [hit("16", "provider duties"), hit("rec", "recital"), hit("26", "deployer duties")]
    ranked = reranker.rerank("companies that use a system", hits, k=2)
    assert [(h.id, h.score) for h in ranked] == [("26", 0.9), ("rec", 0.5)]


def test_the_model_sees_the_header_with_the_text():
    reranker = FakeReranker({"deployer duties": 1.0})
    reranker.rerank("q", [hit("26", "deployer duties")], k=1)
    assert reranker.seen == ["AI Act › Article 26\ndeployer duties"]


def test_no_candidates_means_no_model_call():
    reranker = FakeReranker({})
    assert reranker.rerank("q", [], k=5) == [] and reranker.seen == []


def test_model_is_not_loaded_until_used():
    assert "model" not in Reranker().__dict__  # importing torch costs seconds; tests stay fast
