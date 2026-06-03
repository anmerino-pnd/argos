"""Cliente de embeddings de OpenAI con reintentos y caché para queries."""
from cachetools import TTLCache
from openai import (
    AsyncOpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from typing import cast
from argos.config.settings import get_settings


MAX_INPUT_CHARS = 6000


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_INPUT_CHARS else text[:MAX_INPUT_CHARS]


def _normalize_query(query: str) -> str:
    """Normaliza para que 'Cable UTP' y 'cable utp' hagan hit en el mismo cache slot."""
    return " ".join(query.lower().split())


class Embedder:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

        # Caché solo para queries de búsqueda.
        # 1000 entradas, TTL 1 hora. Si el top-100 de queries representa
        # ~50% del tráfico, capturamos eso con cómodo margen.
        # Memoria estimada: 1000 * 512 floats * 4 bytes ≈ 2 MB. Despreciable.
        self._query_cache: TTLCache[str, list[float]] = cast(
            TTLCache[str, list[float]],
            TTLCache(maxsize=1000, ttl=3600),
        )
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def cache_stats(self) -> dict:
        total = self._cache_hits + self._cache_misses
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "size": len(self._query_cache),
            "hit_rate": self._cache_hits / total if total else 0.0,
        }

    async def embed_query(self, query: str) -> tuple[list[float], bool]:
        """Embebe un query de búsqueda. Devuelve (vector, cache_hit)."""
        key = _normalize_query(query)
        cached = self._query_cache.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached, True

        self._cache_misses += 1
        [vec] = await self.embed_batch([query])
        self._query_cache[key] = vec
        return vec, False

    @retry(
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embebe múltiples textos. SIN caché — para ingest."""
        if not texts:
            return []
        truncated = [_truncate(t) for t in texts]
        resp = await self.client.embeddings.create(
            model=self.model,
            input=truncated,
            dimensions=self.dimensions,
        )
        sorted_data = sorted(resp.data, key=lambda d: d.index)
        return [d.embedding for d in sorted_data]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder