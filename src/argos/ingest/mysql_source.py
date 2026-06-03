"""Lectura paginada de productos desde MySQL de producción."""
from collections.abc import AsyncIterator

import aiomysql

from argos.config.settings import get_settings


# Query con JOINs para traer nombres de marca y categoría.
# Paginamos por p.idProductos > $last_id (keyset pagination) — eficiente en tablas grandes.
QUERY = """
SELECT
    p.idProductos        AS id_producto,
    p.clave              AS clave,
    p.numParte           AS num_parte,
    p.ean                AS ean,
    p.codigoSat          AS codigo_sat,
    p.modelo             AS modelo,
    p.tipo               AS tipo,
    p.descripcion_corta  AS descripcion_corta,
    p.descripcion        AS descripcion,
    p.palabrasClave      AS palabras_clave,
    p.idCategoria        AS id_categoria,
    c.nombre             AS categoria_nombre,
    p.idMarca            AS id_marca,
    m.nombre             AS marca_nombre,
    (p.activo = 1)       AS activo
FROM productos p
LEFT JOIN categorias c ON c.idCategoria = p.idCategoria
LEFT JOIN marcas     m ON m.idMarca     = p.idMarca
WHERE p.idProductos > %s
ORDER BY p.idProductos ASC
LIMIT %s
"""


async def iter_products(
    batch_size: int = 500,
    limit: int | None = None,
) -> AsyncIterator[list[dict]]:
    """Itera productos en batches. Cada batch es una lista de dicts.

    Si `limit` se setea, deja de iterar al llegar a ese total.
    """
    settings = get_settings()
    total = 0
    last_id = 0

    conn = await aiomysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        db=settings.mysql_db,
        charset="utf8",
        autocommit=True,
    )
    try:
        while True:
            page_size = batch_size
            if limit is not None:
                remaining = limit - total
                if remaining <= 0:
                    break
                page_size = min(batch_size, remaining)

            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(QUERY, (last_id, page_size))
                rows = await cur.fetchall()

            if not rows:
                break

            yield rows

            last_id = rows[-1]["id_producto"]
            total += len(rows)
    finally:
        conn.close()