"""Búsqueda híbrida: exact match + tsvector + vector + Reciprocal Rank Fusion."""
import time

from argos.db.connection import get_pool
from argos.ingest.embed import get_embedder


# Pool de candidatos por método antes de fusionar.
# Mayor = mejor recall, peor latencia. 50 es un buen default.
CANDIDATES_PER_METHOD = 50

# Peso del match exacto. Es deliberadamente alto: si alguien tipea
# exactamente un SKU/EAN/parte, ese producto SIEMPRE debe ir arriba.
EXACT_MATCH_WEIGHT = 10.0

# Constante k del paper original de RRF. Vale 60 por tradición.
RRF_K = 60


HYBRID_SQL = """
WITH params AS (
    SELECT
        $1::text                                                AS q_text,
        websearch_to_tsquery('es_unaccent', $1::text)           AS q_tsq,
        $2::vector(512)                                         AS q_vec
),
lex AS (
    SELECT
        p.id_producto,
        ROW_NUMBER() OVER (
            ORDER BY ts_rank_cd(p.search_tsv, params.q_tsq) DESC, p.id_producto
        ) AS rnk
    FROM productos p, params
    WHERE p.activo = TRUE
      AND p.search_tsv @@ params.q_tsq
    ORDER BY ts_rank_cd(p.search_tsv, params.q_tsq) DESC
    LIMIT $3
),
sem AS (
    SELECT
        p.id_producto,
        ROW_NUMBER() OVER (ORDER BY p.embedding <=> params.q_vec) AS rnk
    FROM productos p, params
    WHERE p.activo = TRUE
      AND p.embedding IS NOT NULL
    ORDER BY p.embedding <=> params.q_vec
    LIMIT $3
),
exact AS (
    SELECT p.id_producto
    FROM productos p, params
    WHERE p.activo = TRUE
      AND (
          UPPER(p.clave)      = UPPER(params.q_text) OR
          UPPER(p.num_parte)  = UPPER(params.q_text) OR
          p.ean               = params.q_text        OR
          UPPER(p.codigo_sat) = UPPER(params.q_text)
      )
),
fused AS (
    SELECT id_producto, SUM(weight) AS score
    FROM (
        SELECT id_producto, 1.0 / ($4 + rnk)        AS weight FROM lex
        UNION ALL
        SELECT id_producto, 1.0 / ($4 + rnk)        AS weight FROM sem
        UNION ALL
        SELECT id_producto, $5::float               AS weight FROM exact
    ) all_signals
    GROUP BY id_producto
)
SELECT
    p.id_producto,
    p.clave,
    p.modelo,
    p.tipo,
    p.marca_nombre,
    p.categoria_nombre,
    p.descripcion_corta,
    f.score
FROM fused f
JOIN productos p USING (id_producto)
ORDER BY f.score DESC
LIMIT $6 OFFSET $7;
"""


async def hybrid_search(
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int, bool]:
    """Búsqueda híbrida. Devuelve (resultados, tiempo_ms, cache_hit)."""
    t0 = time.perf_counter()

    embedder = get_embedder()
    q_vec, cache_hit = await embedder.embed_query(query)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            HYBRID_SQL,
            query,
            q_vec,
            CANDIDATES_PER_METHOD,
            RRF_K,
            EXACT_MATCH_WEIGHT,
            limit,
            offset,
        )

    took_ms = int((time.perf_counter() - t0) * 1000)
    return [dict(r) for r in rows], took_ms, cache_hit