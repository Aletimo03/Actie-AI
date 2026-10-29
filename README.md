# Actie AI

Describe the AI system you are building and get a first check against the
EU AI Act (Regulation (EU) 2024/1689): is it prohibited, is it high-risk,
which transparency rules apply, what your obligations are, with every
claim cited to the official text.

> Status: early development. Not legal advice.

## How it works

1. **Ingestion** turns the official AI Act text (EUR-Lex, English and
   Italian) into one chunk per article paragraph or annex point, embeds
   them and stores them in Postgres with pgvector.
2. **Retrieval** finds the relevant chunks with hybrid search (vector +
   full-text, merged with reciprocal rank fusion) and a re-ranker.
3. **The agent** (planned) walks the Act's decision steps and returns a
   report whose citations are verified against the stored text.

## Stack

Python 3.12 · uv · Postgres 16 + pgvector · Ollama (`bge-m3` embeddings) ·
Docker Compose · pytest · ruff

## Local setup

Requirements: [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com).

```bash
cp .env.example .env          # then set a real password (POSTGRES_PASSWORD and DATABASE_URL)
uv sync                       # create .venv and install dependencies
docker compose up -d          # start Postgres + pgvector
ollama pull bge-m3            # embedding model, ~1.2 GB
uv run --env-file .env pytest # run the tests (database tests need the compose stack)
```

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

## Project layout

```
ingestion/              offline pipeline: fetch, parse, chunk, validate, embed, load
backend/app/retrieval/  vector, keyword and hybrid search, re-ranking
db/init/                SQL run once when the database is created
tests/                  pytest suite
```

## License

MIT, see [LICENSE](LICENSE).
