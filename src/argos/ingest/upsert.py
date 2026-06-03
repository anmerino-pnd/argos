"""Upsert en Postgres. Si el content_hash no cambió, conservamos el embedding."""
from argos.db.connection import get_pool
from argos.ingest.transform import ProductRow


UPSERT_SQL = """
INSERT INTO productos (
    id_producto, clave, num_parte, ean, codigo_sat,
    modelo, tipo, descripcion_corta, descripcion, palabras_clave,
    id_categoria, categoria_nombre, id_marca, marca_nombre,
    activo, search_text, content_hash, search_tsv
) VALUES (
    $1, $2, $3, $4, $5,
    $6, $7, $8, $9, $10,
    $11, $12, $13, $14,
    $15, $16, $17, to_tsvector('es_unaccent', $16)
)
ON CONFLICT (id_producto) DO UPDATE SET
    clave             = EXCLUDED.clave,
    num_parte         = EXCLUDED.num_parte,
    ean               = EXCLUDED.ean,
    codigo_sat        = EXCLUDED.codigo_sat,
    modelo            = EXCLUDED.modelo,
    tipo              = EXCLUDED.tipo,
    descripcion_corta = EXCLUDED.descripcion_corta,
    descripcion       = EXCLUDED.descripcion,
    palabras_clave    = EXCLUDED.palabras_clave,
    id_categoria      = EXCLUDED.id_categoria,
    categoria_nombre  = EXCLUDED.categoria_nombre,
    id_marca          = EXCLUDED.id_marca,
    marca_nombre      = EXCLUDED.marca_nombre,
    activo            = EXCLUDED.activo,
    search_text       = EXCLUDED.search_text,
    search_tsv        = to_tsvector('es_unaccent', EXCLUDED.search_text),
    content_hash      = EXCLUDED.content_hash,
    embedding         = CASE WHEN productos.content_hash = EXCLUDED.content_hash
                             THEN productos.embedding ELSE NULL END,
    embedded_at       = CASE WHEN productos.content_hash = EXCLUDED.content_hash
                             THEN productos.embedded_at ELSE NULL END,
    embedding_model   = CASE WHEN productos.content_hash = EXCLUDED.content_hash
                             THEN productos.embedding_model ELSE NULL END
"""


async def upsert_batch(rows: list[ProductRow]) -> None:
    if not rows:
        return
    pool = await get_pool()
    records = [
        (
            r.id_producto, r.clave, r.num_parte, r.ean, r.codigo_sat,
            r.modelo, r.tipo, r.descripcion_corta, r.descripcion, r.palabras_clave,
            r.id_categoria, r.categoria_nombre, r.id_marca, r.marca_nombre,
            r.activo, r.search_text, r.content_hash,
        )
        for r in rows
    ]
    async with pool.acquire() as conn:
        await conn.executemany(UPSERT_SQL, records)


async def fetch_pending_embeddings(
    embedding_model: str,
    chunk_size: int,
) -> list[tuple[int, str]]:
    """Devuelve (id_producto, search_text) de filas sin embedding o con modelo viejo."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id_producto, search_text
            FROM productos
            WHERE embedding IS NULL OR embedding_model IS DISTINCT FROM $1
            ORDER BY id_producto
            LIMIT $2
            """,
            embedding_model,
            chunk_size,
        )
    return [(r["id_producto"], r["search_text"]) for r in rows]


async def save_embeddings(
    items: list[tuple[int, list[float]]],
    embedding_model: str,
) -> None:
    """Guarda embeddings y marca embedded_at/embedding_model."""
    if not items:
        return
    pool = await get_pool()
    records = [(emb, embedding_model, pid) for pid, emb in items]
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            UPDATE productos
            SET embedding = $1,
                embedded_at = NOW(),
                embedding_model = $2
            WHERE id_producto = $3
            """,
            records,
        )

async def soft_delete_missing(seen_ids: set[int]) -> int:
    """Marca como inactivos los productos que ya no están en MySQL.

    Recibe el set completo de id_producto que se vieron en este sync.
    Cualquier producto en Postgres con `activo = TRUE` y cuyo id NO esté
    en seen_ids se considera borrado de la fuente y se soft-deletea.

    Devuelve cuántos productos se marcaron como inactivos.

    IMPORTANTE: SOLO llamar con la lista completa de IDs (sync full).
    Si se llama con una lista parcial, se marcan como inactivos productos
    que en realidad siguen activos en MySQL.
    """
    if not seen_ids:
        # Defensa: no borres nada si la lista viene vacía (probablemente un bug).
        return 0

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            """
            WITH updated AS (
                UPDATE productos
                SET activo = FALSE,
                    updated_at = NOW()
                WHERE activo = TRUE
                  AND id_producto != ALL($1::int[])
                RETURNING id_producto
            )
            SELECT COUNT(*) FROM updated
            """,
            list(seen_ids),
        )
    return int(result or 0)