from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=200, description="Texto de búsqueda")
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1000)


class SearchHit(BaseModel):
    id_producto: int
    clave: str
    modelo: str | None
    tipo: str | None
    marca_nombre: str | None
    categoria_nombre: str | None
    descripcion_corta: str | None
    score: float


class SearchResponse(BaseModel):
    query: str
    took_ms: int
    total: int
    cached: bool = False
    results: list[SearchHit]