# Actie AI

Describe an AI system in a few sentences and see what the EU AI Act
(Regulation (EU) 2024/1689) requires of it: whether it is prohibited or high-risk,
which transparency rules apply, your role, your obligations with the date each one
applies from, and the articles they come from. Every quotation in the report is
checked against the official text. English and Italian.

**Live:** https://13-63-133-200.sslip.io

> Not legal advice. A first check, to know what to ask a lawyer.

## How it works

1. **The law, prepared once.** The consolidated text from EUR-Lex (English and Italian)
   is split into one chunk per article paragraph, point and annex entry, embedded, and
   stored in Postgres with pgvector.
2. **Retrieval.** Vector and keyword search, merged with reciprocal rank fusion and
   re-ranked by a cross-encoder: the right provision is in the top 5 for 92% of the
   test questions.
3. **The assessment.** A LangGraph agent follows the Act's own order: extract the facts,
   ask the user what the description leaves open, check the prohibited practices
   (Art. 5), high-risk classification (Art. 6, Annexes I and III), transparency (Art. 50),
   the role (Art. 25), then list the obligations and verify every citation. Progress
   streams to the browser step by step (Server-Sent Events).
4. **The safeguards.** When a fact is unknown the agent takes the stricter reading and
   says so; an evaluation on 52 labelled systems must show zero under-classifications.

## Stack

| | |
|---|---|
| Agent and API | Python 3.12, uv, LangGraph, LiteLLM (Claude Haiku 5.5), FastAPI, Postgres 16 + pgvector |
| Retrieval | bge-m3 embeddings (Ollama), Postgres full text, bge-reranker-v2-m3 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS + shadcn/ui, Vitest |
| Delivery | Docker, GitHub Actions (tests, image smoke test, Helm checks, GHCR with SBOM), Helm on kind, Terraform on AWS |

## Local setup

Requirements: [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com).

```bash
cp .env.example .env          # then set a real password (POSTGRES_PASSWORD and DATABASE_URL)
uv sync                       # create .venv and install dependencies
docker compose up -d          # start Postgres + pgvector
ollama pull bge-m3            # embedding model, ~1.2 GB
uv run --env-file .env pytest # run the tests (database tests need the compose stack)
```

## Running the app

The whole stack (Postgres, the API, the UI behind nginx) with one command:

```bash
docker compose up -d --build --wait   # then open http://localhost:8080
```

The API reads its settings from `.env` (`LLM_MODEL` and the provider's key, `QUOTA_*`); the
law must be loaded into the database once (see "Ingestion pipeline"), and the `pgdata`
volume keeps it. Only the UI (`127.0.0.1:8080`) and the database (`127.0.0.1:5432`, for
ingestion) are published, both on this machine only. The images run as non-root users;
the API image leaves out the ingestion packages (no torch), the UI image has no Node.
`scripts/compose-smoke.sh` checks the running stack (routes, headers, non-root users, no
ingestion packages, image size budgets); CI runs it on every push.

For development, with reload on every change:

```bash
uv run --env-file .env uvicorn backend.app.api:app --reload  # API on :8000, docs at /docs
cd frontend && npm ci && npm run dev                          # UI on :5173, /api proxied to :8000
```

Requires Node 24 or newer. `frontend/.npmrc` installs only package versions at least
14 days old and runs no install scripts. After changing the API's models, run
`npm run types` in `frontend/` to regenerate `openapi.json` and the TypeScript types;
CI fails if they are stale.

The interface texts are in [`frontend/src/locales/en.json`](frontend/src/locales/en.json)
and [`it.json`](frontend/src/locales/it.json): edit them there, keeping `{placeholders}`
as they are; a test fails if the two languages differ in keys or placeholders.

## Kubernetes (kind)

The same images on a local Kubernetes cluster, deployed with the Helm chart in
[`deploy/helm/actie`](deploy/helm/actie): two API and two UI replicas, Postgres, Traefik
as the ingress, a Job that loads the law, a daily CronJob that deletes assessments
untouched for 30 days, and NetworkPolicies that let only nginx reach the API.

```bash
deploy/kind/up.sh   # needs kind, kubectl, helm; then http://actie.localhost:8088
kind delete cluster --name actie
```

The script tags the images with the commit (plus a hash of uncommitted changes), creates
the `actie-secrets` Secret once from `.env` (the model key) and random values (the quota
secret, the database password), and installs the chart with `values-kind.yaml`. On a real
cluster: `--set image.tag=sha-<commit>` with the images CI publishes to GHCR.
`deploy/helm/check.sh` lints the chart and validates every value combination against the
Kubernetes schemas without a cluster (needs helm and kubeconform); CI runs it on every push.

## AWS

The live site is one EC2 instance in `eu-north-1` running the same images with Compose,
behind Caddy (Let's Encrypt certificate on an sslip.io name), created with Terraform. No
SSH: releases and rollbacks go through Session Manager.

```bash
deploy/aws/deploy.sh <full-commit-sha>   # images CI published for that commit
```

Setup, costs and removal: [`deploy/aws/README.md`](deploy/aws/README.md).

## Ingestion pipeline

Each stage reads the previous stage's files and can be re-run on its own.

```bash
uv run python -m ingestion.fetch      # newest consolidated text + 2024 original, en and it
uv run python -m ingestion.parse      # articles, paragraphs, points, annexes, recitals
uv run python -m ingestion.chunk      # search chunks with context headers + context units
uv run python -m ingestion.validate   # gate: counts, en/it twins, refs, sizes, spot checks
uv run python -m ingestion.embed      # bge-m3 vectors via Ollama, cached by content hash
uv run --env-file .env python -m ingestion.load   # one transaction into Postgres
```

On the consolidated text of 27 July 2026 this gives 1,505 search chunks and
1,023 context units per language. Embedding takes about 3 minutes on an
M-series Mac the first time and about a second on re-runs.

## Retrieval

`backend.app.retrieval.hybrid.search()` runs vector search (bge-m3, pgvector)
and BM25 keyword search (Postgres full text), fuses them with reciprocal rank
fusion, and re-ranks the top 30 with the `BAAI/bge-reranker-v2-m3`
cross-encoder. Scores on the 26-question test set in
[`evals/retrieval_cases.toml`](evals/retrieval_cases.toml) (English and Italian):

| method | recall@5 | recall@10 | recall@20 | MRR |
|---|---|---|---|---|
| vector | 0.73 | 0.77 | 0.85 | 0.48 |
| keyword (BM25) | 0.38 | 0.38 | 0.62 | 0.26 |
| hybrid (RRF) | 0.54 | 0.85 | 0.92 | 0.41 |
| hybrid, binding text only | 0.65 | 0.88 | 0.96 | 0.46 |
| **hybrid + re-ranker** | **0.92** | **0.96** | **0.96** | **0.66** |

```bash
uv run --env-file .env python -m evals.retrieval
```

The re-ranker downloads about 2.3 GB on first use and takes about 3 s per
question on an M-series GPU.

## Agent eval

52 labelled systems ([`evals/systems.toml`](evals/systems.toml)) run through the whole
agent; the gate is **zero under-classifications** (a system reported at a lower risk
than its label), and the script exits 1 otherwise.

```bash
uv run --env-file .env python -m evals.systems --quick   # ~15 systems
uv run --env-file .env python -m evals.systems           # all 52
```

On Claude Haiku 5.5 a run costs about $0.08 (quick) or $0.27 (full) without the reply
cache, so CI never runs it by itself: start it from **Actions → Eval → Run workflow**,
with `ANTHROPIC_API_KEY` stored as a secret of the `eval` environment. It needs no ingestion:
[`db/law_snapshot.jsonl.gz`](db/law_snapshot.jsonl.gz) holds the law the agent
reads (0.9 MB, no embeddings); `python -m backend.app.law_snapshot export` refreshes it after
loading a new version of the law, and a test fails until you do.

## Project layout

```
ingestion/              offline pipeline: fetch, parse, chunk, validate, embed, load
backend/app/retrieval/  vector, keyword and hybrid search, re-ranking
backend/app/agent/      the LangGraph assessment: checks, role, obligations, citations
backend/app/api.py      HTTP API: start, answer, continue, stream progress (SSE)
deploy/                 Helm chart (helm/actie), kind cluster (kind/), AWS (aws/)
frontend/               React UI; src/api/ holds the client and the generated types,
                        src/locales/ the EN/IT texts; Dockerfile and nginx/ for the image
db/init/                SQL run once when the database is created
tests/                  pytest suite
```

## License

MIT, see [LICENSE](LICENSE).
