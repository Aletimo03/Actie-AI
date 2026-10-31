import os
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from test_graph import CLEAR, HIGH, KNOWN, NONE, TODAY, UNKNOWN, ScriptedLLM, fetch, lookup

from backend.app.agent.graph import SERDE, build_graph
from backend.app.api import app, get_graph, get_pool
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
