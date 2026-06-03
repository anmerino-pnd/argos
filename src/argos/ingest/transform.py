"""Transformación: de fila MySQL cruda a fila lista para Postgres."""
import hashlib
from dataclasses import dataclass


@dataclass
class ProductRow:
    """Una fila ya transformada, lista para upsert en Postgres."""
    id_producto: int
    clave: str
    num_parte: str | None
    ean: str | None
    codigo_sat: str | None
    modelo: str | None
    tipo: str | None
    descripcion_corta: str | None
    descripcion: str | None
    palabras_clave: str | None
    id_categoria: int
    categoria_nombre: str | None
    id_marca: int
    marca_nombre: str | None
    activo: bool
    search_text: str
    content_hash: str


def _clean(value: str | None) -> str:
    """Normaliza un campo de texto: strip, colapsa espacios, devuelve '' si vacío."""
    if value is None:
        return ""
    # Postgres no permite el byte NUL (0x00) en columnas text/varchar.
    # MySQL sí lo guarda, así que lo eliminamos aquí.
    s = str(value).replace("\x00", "")
    return " ".join(s.split()).strip()


def build_search_text(row: dict) -> str:
    """Construye el texto curado que se va a embeber y a indexar (tsvector).

    El orden importa: ponemos primero lo más distintivo (marca, modelo, clave)
    para que pese más en el embedding y en tsvector.
    """
    parts = [
        ("Marca", _clean(row.get("marca_nombre"))),
        ("Categoría", _clean(row.get("categoria_nombre"))),
        ("Tipo", _clean(row.get("tipo"))),
        ("Modelo", _clean(row.get("modelo"))),
        ("Clave", _clean(row.get("clave"))),
        ("Número de parte", _clean(row.get("num_parte"))),
        ("EAN", _clean(row.get("ean"))),
        ("Descripción", _clean(row.get("descripcion_corta")) or _clean(row.get("descripcion"))),
        ("Palabras clave", _clean(row.get("palabras_clave"))),
    ]
    return " | ".join(f"{label}: {val}" for label, val in parts if val)


def compute_hash(search_text: str) -> str:
    """SHA-256 del search_text. Si cambia → re-embeber."""
    return hashlib.sha256(search_text.encode("utf-8")).hexdigest()


def transform(row: dict) -> ProductRow:
    """Toma una fila tal como sale de MySQL y la deja lista para Postgres."""
    search_text = build_search_text(row)
    return ProductRow(
        id_producto=int(row["id_producto"]),
        clave=_clean(row.get("clave")),
        num_parte=_clean(row.get("num_parte")) or None,
        ean=_clean(row.get("ean")) or None,
        codigo_sat=_clean(row.get("codigo_sat")) or None,
        modelo=_clean(row.get("modelo")) or None,
        tipo=_clean(row.get("tipo")) or None,
        descripcion_corta=_clean(row.get("descripcion_corta")) or None,
        descripcion=_clean(row.get("descripcion")) or None,
        palabras_clave=_clean(row.get("palabras_clave")) or None,
        id_categoria=int(row["id_categoria"]),
        categoria_nombre=_clean(row.get("categoria_nombre")) or None,
        id_marca=int(row["id_marca"]),
        marca_nombre=_clean(row.get("marca_nombre")) or None,
        activo=bool(row.get("activo", True)),
        search_text=search_text,
        content_hash=compute_hash(search_text),
    )

