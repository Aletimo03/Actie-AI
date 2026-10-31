import json
import os
import uuid
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_graph import CLEAR, HIGH, KNOWN, NONE, TODAY, UNKNOWN, ScriptedLLM, fetch, lookup

from backend.app.agent.graph import SERDE, build_graph
from backend.app.api import app, check_quota, get_graph, get_pool
from backend.app.llm import SchemaError

DESCRIPTION = "We built a tool that ranks job applicants' CVs for recruiters."


def scripted(**replies) -> ScriptedLLM:
    """A paused-then-answered CV ranker unless told otherwise."""
    defaults = dict(
        Facts=[UNKNOWN, KNOWN], ProhibitedCheck=[CLEAR], HighRiskCheck=[HIGH],
        TransparencyCheck=[NONE],
    )  # fmt: skip
    return ScriptedLLM(**defaults | replies)


def graph_over(llm, checkpointer=None):
    return build_graph(
        llm, fetch, lookup, checkpointer or InMemorySaver(serde=SERDE), today=lambda: TODAY
    )


@pytest.fixture
def client():
    app.dependency_overrides[check_quota] = lambda: None  # limits: tests/test_quota.py
    yield TestClient(app)  # no `with`: the lifespan (real pools, real LLM) never runs
    app.dependency_overrides.clear()


def serve(graph) -> None:
    app.dependency_overrides[get_graph] = lambda: graph


def test_a_vague_system_pauses_then_the_answers_finish_the_report(client):
    serve(graph_over(scripted()))
    started = client.post("/assessments", json={"description": DESCRIPTION})
    assert started.status_code == 201
    body = started.json()
    assert body["status"] == "needs_answers" and body["report"] is None
    assert [q["id"] for q in body["questions"]] == [
        "purpose", "domain", "affected_people", "role",
    ]  # fmt: skip
    assert uuid.UUID(body["id"]).version == 4  # unguessable: the id is the key to the data

    assert client.get(f"/assessments/{body['id']}").json() == body  # reading changes nothing

    done = client.post(
        f"/assessments/{body['id']}/answers", json={"answers": {"purpose": "Ranks CVs."}}
    )
    assert done.status_code == 200
    assert done.json()["status"] == "done" and done.json()["report"]["risk"] == "high"


def test_left_out_questions_are_sent_blank_so_the_run_still_resumes(client):
    serve(graph_over(scripted()))
    id = client.post("/assessments", json={"description": DESCRIPTION}).json()["id"]
    assert client.post(f"/assessments/{id}/answers", json={"answers": {}}).json()["status"] == (
        "done"
    )


def test_a_clear_system_reports_at_once(client):
    serve(graph_over(scripted(Facts=[KNOWN])))
    body = client.post("/assessments", json={"description": DESCRIPTION, "lang": "it"}).json()
    assert body["status"] == "done" and body["questions"] == []


@pytest.mark.parametrize(
    "request_body",
    [
        {"description": "Too short."},
        {"description": "x" * 4001},
        {"description": DESCRIPTION, "lang": "de"},
    ],
)
def test_bad_requests_never_reach_the_graph(client, request_body):
    llm = scripted()
    serve(graph_over(llm))
    assert client.post("/assessments", json=request_body).status_code == 422
    assert llm.prompts == []


def test_unknown_and_finished_assessments(client):
    serve(graph_over(scripted(Facts=[KNOWN])))
    missing = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/assessments/{missing}").status_code == 404
    assert client.post(f"/assessments/{missing}/answers", json={"answers": {}}).status_code == 404

    id = client.post("/assessments", json={"description": DESCRIPTION}).json()["id"]
    finished = client.post(f"/assessments/{id}/answers", json={"answers": {}})
    assert finished.status_code == 409 and "done" in finished.json()["detail"]


def test_a_provider_failure_is_503_and_the_paused_state_is_kept(client):
    class Down(ScriptedLLM):
        def ask(self, system, user, schema):
            if schema.__name__ == "ProhibitedCheck":
                raise SchemaError("ProhibitedCheck: no valid reply after 2 attempts")
            return super().ask(system, user, schema)

    serve(graph_over(Down(Facts=[UNKNOWN, KNOWN])))
    id = client.post("/assessments", json={"description": DESCRIPTION}).json()["id"]
    failed = client.post(f"/assessments/{id}/answers", json={"answers": {}})
    assert failed.status_code == 503 and failed.headers["retry-after"] == "60"
    assert client.get(f"/assessments/{id}").json()["status"] == "incomplete"


def events(response) -> list[tuple[str, dict]]:
    """The (event, data) pairs of a Server-Sent Events body."""
    pairs = []
    for block in response.text.strip().split("\n\n"):
        name, data = block.split("\n")
        pairs.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return pairs


def test_streaming_sends_each_step_then_the_same_result_as_the_json_endpoint(client):
    serve(graph_over(scripted()))
    paused = client.post("/assessments/stream", json={"description": DESCRIPTION, "lang": "it"})
    assert paused.headers["content-type"].startswith("text/event-stream")
    assert paused.headers["x-accel-buffering"] == "no"  # or nginx holds every event back
    sent = events(paused)
    (_, start), *steps, (last, result) = sent
    assert [d["label"] for _, d in steps] == ["Lettura della descrizione"]
    assert last == "result" and result["status"] == "needs_answers"
    assert client.get(f"/assessments/{start['id']}").json() == result

    done = events(client.post(f"/assessments/{start['id']}/answers/stream", json={"answers": {}}))
    assert [d["step"] for name, d in done if name == "step"] == [
        "extract_facts", "check_prohibited", "check_high_risk", "check_transparency",
        "determine_role", "list_obligations", "verify_citations", "report",
    ]  # fmt: skip
    assert done[-1][0] == "result" and done[-1][1]["report"]["risk"] == "high"


def test_a_failure_after_the_stream_opens_is_an_error_event(client):
    class Down(ScriptedLLM):
        def ask(self, system, user, schema):
            raise SchemaError("Facts: no valid reply after 2 attempts")

    serve(graph_over(Down()))
    sent = events(client.post("/assessments/stream", json={"description": DESCRIPTION}))
    assert [name for name, _ in sent] == ["start", "error"]
    assert sent[1][1]["retry_after"] == 60


def test_streamed_answers_check_the_assessment_before_the_stream_opens(client):
    serve(graph_over(scripted(Facts=[KNOWN])))

    def answer(id):
        return client.post(f"/assessments/{id}/answers/stream", json={"answers": {}})

    assert answer("00000000-0000-4000-8000-000000000000").status_code == 404
    id = client.post("/assessments", json={"description": DESCRIPTION}).json()["id"]
    assert answer(id).status_code == 409


def test_over_the_limit_is_429_before_the_graph_runs(client):
    llm = scripted()
    serve(graph_over(llm))

    def exceeded():
        raise HTTPException(429, "limit reached", headers={"Retry-After": "120"})

    app.dependency_overrides[check_quota] = exceeded
    for path in ("/assessments", "/assessments/stream"):
        refused = client.post(path, json={"description": DESCRIPTION})
        assert refused.status_code == 429 and refused.headers["retry-after"] == "120"
    assert llm.prompts == []


def test_health_reports_the_database(client):
    class Pool:
        def __init__(self, error=None):
            self.error = error

        @contextmanager
        def connection(self, timeout):
            if self.error:
                raise self.error
            yield type("Conn", (), {"execute": lambda self, sql: None})()

    app.dependency_overrides[get_pool] = lambda: Pool()
    assert client.get("/health").json() == {"status": "ok"}
    app.dependency_overrides[get_pool] = lambda: Pool(TimeoutError("no connection"))
    assert client.get("/health").status_code == 503


@pytest.fixture
def checkpoint_db():
    """Connections to a throwaway schema, set up like the API's checkpoint pool."""
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("needs DATABASE_URL (uv run --env-file .env pytest)")
    try:
        admin = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("database not running (docker compose up -d)")
    schema = f"test_{uuid.uuid4().hex[:8]}"
    admin.execute(f"CREATE SCHEMA {schema}")
    opened = []

    def connect():
        conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)
        conn.execute(f"SET search_path TO {schema}")
        opened.append(conn)
        return conn

    yield connect
    for conn in opened:
        conn.close()
    admin.execute(f"DROP SCHEMA {schema} CASCADE")
    admin.close()


def test_a_paused_assessment_survives_a_restart(client, checkpoint_db):
    from langgraph.checkpoint.postgres import PostgresSaver

    llm = scripted()
    before = PostgresSaver(checkpoint_db(), serde=SERDE)
    before.setup()
    serve(graph_over(llm, before))
    id = client.post("/assessments", json={"description": DESCRIPTION}).json()["id"]

    # A new process: new connection, new checkpointer, new graph; only Postgres is shared.
    serve(graph_over(llm, PostgresSaver(checkpoint_db(), serde=SERDE)))
    assert client.get(f"/assessments/{id}").json()["status"] == "needs_answers"
    done = client.post(f"/assessments/{id}/answers", json={"answers": {"role": "We use it."}})
    assert done.json()["status"] == "done" and done.json()["report"]["risk"] == "high"
