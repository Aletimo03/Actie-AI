from datetime import timedelta

from langgraph.checkpoint.postgres import PostgresSaver
from test_api import DESCRIPTION, graph_over, scripted
from test_graph import CLEAR, HIGH, KNOWN, NONE

from backend.app.agent.graph import SERDE
from backend.app.quota import now
from backend.app.retention import purge, stale_threads


def test_only_assessments_untouched_for_the_period_are_deleted(checkpoint_db):
    conn = checkpoint_db()
    saver = PostgresSaver(conn, serde=SERDE)
    saver.setup()
    two = scripted(
        Facts=[KNOWN] * 2, ProhibitedCheck=[CLEAR] * 2, HighRiskCheck=[HIGH] * 2,
        TransparencyCheck=[NONE] * 2,
    )  # fmt: skip
    graph = graph_over(two, saver)

    def config(thread):
        return {"configurable": {"thread_id": thread}}

    for thread in ("old", "recent"):
        graph.invoke({"description": DESCRIPTION, "lang": "en"}, config(thread))
    # Age every checkpoint of "old" by 40 days, as if nobody had opened it since.
    conn.execute(
        "UPDATE checkpoints SET checkpoint = jsonb_set(checkpoint, '{ts}', "
        "to_jsonb(((checkpoint->>'ts')::timestamptz - interval '40 days')::text)) "
        "WHERE thread_id = 'old'"
    )
    cutoff = now() - timedelta(days=30)
    assert stale_threads(conn, cutoff) == ["old"]

    assert purge(conn, cutoff) == ["old"]
    assert not graph.get_state(config("old")).values
    assert graph.get_state(config("recent")).values["report"]
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        count = conn.execute(f"SELECT count(*) AS n FROM {table} WHERE thread_id = 'old'")
        assert count.fetchone()["n"] == 0
