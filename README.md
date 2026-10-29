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
uv run pytest                 # run the tests
```

## Project layout

```
ingestion/              offline pipeline: fetch, parse, chunk, validate, embed, load
backend/app/retrieval/  vector, keyword and hybrid search, re-ranking
db/init/                SQL run once when the database is created
tests/                  pytest suite
```

## License

MIT, see [LICENSE](LICENSE).
