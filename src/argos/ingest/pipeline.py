"""Pipeline: lee MySQL → upsert → embed pendientes → guarda embeddings."""
import logging
import time

from argos.config.settings import get_settings
from argos.ingest.embed import Embedder
from argos.ingest.mysql_source import iter_products
from argos.ingest.transform import transform
from argos.ingest.upsert import (
    fetch_pending_embeddings,
    soft_delete_missing,
    save_embeddings,
    upsert_batch,
)

log = logging.getLogger(__name__)


async def stage_sync_from_mysql() -> tuple[int, int]:
    """Etapa 1: trae productos de MySQL y los upsertea en Postgres.

    Si NO hay sample limit (sync completo), también detecta borrados:
    productos que ya no están en MySQL se marcan como `activo = false` en
    Postgres. Si hay sample limit, se omite el soft-delete por seguridad.

    Devuelve (upserted_count, soft_deleted_count).
    """
    settings = get_settings()
    seen_ids: set[int] = set()
    total = 0
    t0 = time.perf_counter()

    async for raw_batch in iter_products(
        batch_size=settings.ingest_batch_size,
        limit=settings.ingest_sample_limit,
    ):
        rows = [transform(r) for r in raw_batch]
        await upsert_batch(rows)
        seen_ids.update(r.id_producto for r in rows)
        total += len(rows)
        log.info("upsert: %d productos (acum %d)", len(rows), total)

    log.info(
        "sync MySQL→PG terminado: %d productos en %.1fs",
        total,
        time.perf_counter() - t0,
    )

    # Soft-delete solo si fue un sync completo.
    soft_deleted = 0
    if settings.ingest_sample_limit is None:
        soft_deleted = await soft_delete_missing(seen_ids)
        if soft_deleted > 0:
            log.info("soft-delete: %d productos marcados como inactivos", soft_deleted)
    else:
        log.info("sample limit activo, skipping soft-delete por seguridad")

    return total, soft_deleted


async def stage_embed_pending() -> int:
    """Etapa 2: encuentra productos sin embedding y los embebe en batches."""
    settings = get_settings()
    embedder = Embedder()
    total = 0
    t0 = time.perf_counter()

    while True:
        pending = await fetch_pending_embeddings(
            embedding_model=settings.embedding_model,
            chunk_size=settings.embedding_batch_size,
        )
        if not pending:
            break

        ids = [pid for pid, _ in pending]
        texts = [txt for _, txt in pending]

        vectors = await embedder.embed_batch(texts)
        await save_embeddings(list(zip(ids, vectors)), settings.embedding_model)

        total += len(pending)
        log.info("embed: %d productos (acum %d)", len(pending), total)

    log.info("embedding terminado: %d productos en %.1fs", total, time.perf_counter() - t0)
    return total


async def run_full_ingest() -> tuple[int, int, int]:
    """Devuelve (upserted, soft_deleted, embedded)."""
    upserted, soft_deleted = await stage_sync_from_mysql()
    embedded = await stage_embed_pending()
    return upserted, soft_deleted, embedded