"""Argos search API."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from argos.ingest.embed import get_embedder
from argos.search.hybrid import hybrid_search
from argos.db.connection import close_pool, get_pool
from argos.search.schemas import SearchHit, SearchRequest, SearchResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    get_embedder()  # crea el cliente httpx una vez al arrancar
    yield
    await close_pool()


app = FastAPI(
    title="Argos",
    description="Motor de búsqueda híbrido para el catálogo de CT Internacional",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    rows, took_ms, cached = await hybrid_search(
        req.q, limit=req.limit, offset=req.offset
    )
    return SearchResponse(
        query=req.q,
        took_ms=took_ms,
        total=len(rows),
        cached=cached,
        results=[SearchHit(**r) for r in rows],
    )


@app.get("/search", response_model=SearchResponse)
async def search_get(q: str, limit: int = 20, offset: int = 0) -> SearchResponse:
    return await search(SearchRequest(q=q, limit=limit, offset=offset))


@app.get("/stats")
async def stats() -> dict:
    return {"embedding_cache": get_embedder().cache_stats}