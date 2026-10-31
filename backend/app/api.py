"""HTTP API: one assessment is one LangGraph thread, started and resumed over HTTP.

POST /assessments runs the graph until it pauses with questions or ends with
the report; POST /assessments/{id}/answers resumes it from its checkpoint;
GET /assessments/{id} reads it. The checkpoints live in Postgres, so a paused
assessment survives a restart and any server can resume it.

Endpoints are plain `def`: the graph blocks (LiteLLM, psycopg), and FastAPI
runs `def` endpoints in a thread pool, where `async def` would freeze every
other request for the 20-40 s of a report.

    uv run --env-file .env uvicorn backend.app.api:app --reload
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import uuid4

import litellm
from fastapi import Depends, FastAPI, HTTPException, Request
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from backend.app.agent.citations import fetch_chunks
from backend.app.agent.graph import SERDE, build_graph
from backend.app.llm import LLM, SchemaError
from backend.app.retrieval.contexts import fetch_contexts

# Failures of the model provider, not of the request: the user can try again later.
UNAVAILABLE = (
    SchemaError,
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
    litellm.Timeout,
)
RETRY_AFTER = "60"  # seconds; a daily cap lasts longer, but the client cannot tell which


class AssessRequest(BaseModel):
    # The upper bound limits the cost of each call and the room for prompt injection.
    description: str = Field(min_length=20, max_length=4000)
    lang: Literal["en", "it"] = "en"


class AnswersRequest(BaseModel):
    # Question id -> answer. Questions left out or blank are skipped.
    answers: dict[str, Annotated[str, Field(max_length=1000)]] = Field(max_length=20)


class QuestionOut(BaseModel):
    id: str
    text: str


class AssessmentOut(BaseModel):
    id: str
    # incomplete: a provider error stopped the run between two checkpoints
    status: Literal["needs_answers", "done", "incomplete"]
    questions: list[QuestionOut] = []
    report: dict | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    url = os.environ["DATABASE_URL"]
    # Two pools: the checkpointer needs autocommit and dict rows, the law queries read tuples.
    checkpoints = ConnectionPool(
        url, min_size=1, max_size=10, kwargs={"autocommit": True, "row_factory": dict_row}
    )
    law = ConnectionPool(url, min_size=1, max_size=10)
    checkpointer = PostgresSaver(checkpoints, serde=SERDE)
    checkpointer.setup()  # creates or migrates its tables; safe on every start

    def fetch(ids: list[str]):
        with law.connection() as conn:
            return fetch_contexts(conn, ids)

    def lookup(ids: list[str]):
        with law.connection() as conn:
            return fetch_chunks(conn, ids)

    # No disk cache here, whatever LLM_CACHE_DIR says: it would keep users' descriptions.
    app.state.graph = build_graph(LLM(cache_dir=None), fetch, lookup, checkpointer)
    app.state.pool = law
    try:
        yield
    finally:
        law.close()
        checkpoints.close()


app = FastAPI(title="Actie AI", lifespan=lifespan)


def get_graph(request: Request):
    return request.app.state.graph


def get_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


Graph = Annotated[object, Depends(get_graph)]


def config(id: str) -> dict:
    return {"configurable": {"thread_id": id}}


def outcome(graph, id: str) -> AssessmentOut:
    """The assessment as its latest checkpoint shows it."""
    snapshot = graph.get_state(config(id))
    if not snapshot.values:
        raise HTTPException(404, "assessment not found")
    if report := snapshot.values.get("report"):
        return AssessmentOut(id=id, status="done", report=report)
    if snapshot.interrupts:
        questions = snapshot.interrupts[0].value["questions"]
        return AssessmentOut(id=id, status="needs_answers", questions=questions)
    return AssessmentOut(id=id, status="incomplete")


def run(graph, value, id: str) -> AssessmentOut:
    try:
        graph.invoke(value, config(id))
    except UNAVAILABLE as error:
        raise HTTPException(
            503,
            f"the language model is unavailable ({type(error).__name__}); try again later",
            headers={"Retry-After": RETRY_AFTER},
        ) from error
    return outcome(graph, id)


@app.post("/assessments", status_code=201)
def start(request: AssessRequest, graph: Graph) -> AssessmentOut:
    id = str(uuid4())  # unguessable: the id is the key to the description and answers
    return run(graph, {"description": request.description, "lang": request.lang}, id)


@app.post("/assessments/{id}/answers")
def answer(id: str, request: AnswersRequest, graph: Graph) -> AssessmentOut:
    current = outcome(graph, id)
    if current.status != "needs_answers":
        raise HTTPException(409, f"the assessment is {current.status}, not waiting for answers")
    # Every pending question gets a reply, blank if skipped: an empty dict would not resume.
    replies = {q.id: request.answers.get(q.id, "").strip() for q in current.questions}
    return run(graph, Command(resume=replies), id)


@app.get("/assessments/{id}")
def read(id: str, graph: Graph) -> AssessmentOut:
    return outcome(graph, id)


@app.get("/health")
def health(pool: Annotated[ConnectionPool, Depends(get_pool)]) -> dict:
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except Exception as error:
        raise HTTPException(503, "database unavailable") from error
    return {"status": "ok"}
