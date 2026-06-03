"""CLI para probar búsqueda. Uso: uv run python scripts/search_cli.py "tu query" [limit]"""
import asyncio
import sys

from argos.db.connection import close_pool
from argos.search.hybrid import hybrid_search


async def main(query: str, limit: int) -> None:
    try:
        rows, took_ms, _ = await hybrid_search(query, limit=limit)
        print(f'\nQuery: "{query}"  →  {len(rows)} resultados en {took_ms} ms\n')
        print(f"{'score':>8}  {'clave':12}  {'marca':18}  {'modelo':25}  descripción")
        print("-" * 110)
        for r in rows:
            modelo = (r["modelo"] or "")[:25]
            marca = (r["marca_nombre"] or "")[:18]
            desc = (r["descripcion_corta"] or r["tipo"] or "")[:50]
            print(f"  {r['score']:.4f}  {r['clave']:12}  {marca:18}  {modelo:25}  {desc}")
    finally:
        await close_pool()


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "cable utp"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    asyncio.run(main(q, n))