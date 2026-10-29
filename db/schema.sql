-- Actie AI database schema. Applied by the load step on every run, so every
-- statement is idempotent (IF NOT EXISTS). A version is the CELEX number of
-- the consolidated text the rows come from, e.g. 02024R1689-20260727.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS versions (
    version     text PRIMARY KEY,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    is_current  boolean NOT NULL DEFAULT false
);

-- At most one current version: retrieval reads only that one.
CREATE UNIQUE INDEX IF NOT EXISTS versions_one_current ON versions (is_current) WHERE is_current;

-- What the LLM reads: a paragraph with its points, a top-level point, a recital.
CREATE TABLE IF NOT EXISTS contexts (
    id       text NOT NULL,
    version  text NOT NULL REFERENCES versions ON DELETE CASCADE,
    lang     text NOT NULL CHECK (lang IN ('en', 'it')),
    header   text NOT NULL,
    text     text NOT NULL,
    source   text NOT NULL,
    PRIMARY KEY (id, version)
);

-- What retrieval searches: one row per node with its own text.
CREATE TABLE IF NOT EXISTS chunks (
    id               text NOT NULL,
    version          text NOT NULL REFERENCES versions ON DELETE CASCADE,
    lang             text NOT NULL CHECK (lang IN ('en', 'it')),
    kind             text NOT NULL,
    header           text NOT NULL,
    text             text NOT NULL,
    embed_text       text NOT NULL,
    context_id       text NOT NULL,
    article          text NOT NULL DEFAULT '',
    paragraph        text NOT NULL DEFAULT '',
    annex            text NOT NULL DEFAULT '',
    chapter          text NOT NULL DEFAULT '',
    refs             text[] NOT NULL DEFAULT '{}',
    binding          boolean NOT NULL,
    amended          boolean NOT NULL,
    source           text NOT NULL,
    content_hash     text NOT NULL,  -- sha256 of model + embed_text: reuse the vector if unchanged
    embedding        vector(1024) NOT NULL,
    embedding_model  text NOT NULL,
    -- Keyword search column, kept in sync by Postgres with the language's stemming rules.
    tsv tsvector GENERATED ALWAYS AS (
        to_tsvector(
            CASE lang WHEN 'it' THEN 'italian'::regconfig ELSE 'english'::regconfig END,
            embed_text
        )
    ) STORED,
    PRIMARY KEY (id, version),
    FOREIGN KEY (context_id, version) REFERENCES contexts (id, version) ON DELETE CASCADE
);

-- Approximate nearest-neighbour search by cosine distance (embedding <=> query).
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_article ON chunks (version, lang, article);
CREATE INDEX IF NOT EXISTS chunks_annex ON chunks (version, lang, annex);
CREATE INDEX IF NOT EXISTS chunks_content_hash ON chunks (content_hash);
