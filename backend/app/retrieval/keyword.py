"""Keyword search: BM25 over the generated tsv column, computed in SQL.

The question is reduced to stemmed lexemes with the chunks' own dictionary
(english or italian). Postgres' built-in ts_rank has no notion of how rare a
word is, and every chunk contains "ai", "act" and "articl" through its
context header, so those words drowned the useful ones ("emot" is in 11 of
1505 chunks). BM25 weights each lexeme by its inverse document frequency:

    score = sum over query lexemes of  idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len / avglen))
    idf   = ln(1 + (N - df + 0.5) / (df + 0.5))

tf is how often the lexeme occurs in the chunk, len the chunk's lexeme count.
"""

import psycopg

from backend.app.retrieval.vector import CURRENT_VERSION, Hit

CONFIG = {"en": "english", "it": "italian"}
K1 = 1.2  # how quickly repeated occurrences stop adding score (the usual default)
B = 0.75  # how much long chunks are penalised (the usual default)

BM25_SQL = f"""
WITH q AS (
    SELECT DISTINCT lexeme
    FROM unnest(tsvector_to_array(to_tsvector(%(config)s::regconfig, %(query)s))) AS lexeme
),
docs AS (
    SELECT id, header, text, context_id, tsv, length(tsv) AS len
    FROM chunks
    WHERE version = {CURRENT_VERSION} AND lang = %(lang)s
),
corpus AS (SELECT count(*) AS n, avg(len) AS avglen FROM docs),
tf AS (
    SELECT d.id, t.lexeme, cardinality(t.positions) AS tf, d.len
    FROM docs d, unnest(d.tsv) AS t
    WHERE t.lexeme IN (SELECT lexeme FROM q)
),
df AS (SELECT lexeme, count(*) AS df FROM tf GROUP BY lexeme),
scores AS (
    SELECT tf.id,
           sum(ln(1 + (c.n - df.df + 0.5) / (df.df + 0.5))
               * tf.tf * (%(k1)s + 1)
               / (tf.tf + %(k1)s * (1 - %(b)s + %(b)s * tf.len / c.avglen))) AS score
    FROM tf JOIN df USING (lexeme) CROSS JOIN corpus c
    GROUP BY tf.id
)
SELECT d.id, s.score, d.header, d.text, d.context_id
FROM scores s JOIN docs d USING (id)
ORDER BY s.score DESC, d.id
LIMIT %(k)s
"""


def keyword_search(conn: psycopg.Connection, query: str, lang: str, k: int = 10) -> list[Hit]:
    params = {"config": CONFIG[lang], "query": query, "lang": lang, "k": k, "k1": K1, "b": B}
    return [Hit(*row) for row in conn.execute(BM25_SQL, params).fetchall()]
