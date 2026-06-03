"""Pool asyncpg con registro del tipo vector de pgvector."""
import asyncpg
from pgvector.asyncpg import register_vector

from argos.config.settings import get_settings

_pool: asyncpg.Pool | None = None


def _asyncpg_dsn(database_url: str) -> str:
    """asyncpg no entiende el prefijo de SQLAlchemy. Lo normalizamos."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            _asyncpg_dsn(settings.database_url),
            min_size=2,
            max_size=10,
            init=_init_connection,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None