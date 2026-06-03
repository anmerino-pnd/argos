"""Test del soft-delete. Requiere Postgres corriendo (compose up)."""
import pytest
import pytest_asyncio

from argos.db.connection import get_pool
from argos.ingest.upsert import soft_delete_missing


@pytest_asyncio.fixture
async def db_with_test_products():
    """Inserta 3 productos sintéticos con IDs negativos (no colisionan con reales)
    y devuelve el set de IDs reales activos para que el test los incluya en
    `seen_ids` y NO los marque como inactivos por accidente.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO productos (
                id_producto, clave, id_categoria, id_marca, activo,
                search_text, content_hash
            ) VALUES
                (-1, 'TEST_A', 1, 1, TRUE,  'a', 'a'),
                (-2, 'TEST_B', 1, 1, TRUE,  'b', 'b'),
                (-3, 'TEST_C', 1, 1, TRUE,  'c', 'c')
            ON CONFLICT (id_producto) DO UPDATE
                SET activo = TRUE
        """)
        existing = await conn.fetch(
            "SELECT id_producto FROM productos "
            "WHERE id_producto > 0 AND activo = TRUE"
        )
    real_active_ids = {r["id_producto"] for r in existing}
    yield real_active_ids
    # Limpieza: borra los productos sintéticos
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM productos WHERE id_producto < 0")


@pytest.mark.asyncio
async def test_soft_delete_marks_missing(db_with_test_products):
    """Simula un sync donde MySQL devolvió todos los reales + TEST_A + TEST_B,
    pero NO TEST_C. Solo TEST_C debe quedar inactivo.
    """
    real_active_ids = db_with_test_products
    seen = real_active_ids | {-1, -2}  # TEST_C deliberadamente ausente
    count = await soft_delete_missing(seen)
    assert count == 1, f"esperaba 1 soft-delete, hubo {count}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id_producto, activo FROM productos "
            "WHERE id_producto < 0 ORDER BY id_producto DESC"
        )
    activos = {r["id_producto"]: r["activo"] for r in rows}
    assert activos == {-1: True, -2: True, -3: False}


@pytest.mark.asyncio
async def test_soft_delete_empty_set_does_nothing():
    """Defensa: lista vacía no debe borrar nada (evita el accidente
    catastrófico de marcar todo como inactivo)."""
    count = await soft_delete_missing(set())
    assert count == 0