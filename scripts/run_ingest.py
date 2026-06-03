"""Ejecuta el ingest. Uso: uv run python scripts/run_ingest.py"""
import asyncio
import logging
import sys

from argos.db.connection import close_pool
from argos.ingest.pipeline import run_full_ingest


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        upserted, soft_deleted, embedded = await run_full_ingest()
        print(
            f"\n✓ Sync: {upserted} productos | "
            f"Soft-delete: {soft_deleted} | "
            f"Embed: {embedded}"
        )
    finally:
        await close_pool()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)