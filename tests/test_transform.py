from argos.ingest.transform import transform, build_search_text, compute_hash


def test_transform_basic():
    row = {
        "id_producto": 3,
        "clave": "ACC3M030",
        "num_parte": "",
        "ean": "0",
        "codigo_sat": None,
        "modelo": "MQ300000667",
        "tipo": "Pantalla de Proyección",
        "descripcion_corta": None,
        "descripcion": "Dimensiones: Pared 2.14 X 2.14 mts",
        "palabras_clave": None,
        "id_categoria": 116,
        "categoria_nombre": "Pantallas de Proyección",
        "id_marca": 3,
        "marca_nombre": "3M",
        "activo": True,
    }
    result = transform(row)
    assert result.id_producto == 3
    assert "3M" in result.search_text
    assert "Pantalla de Proyección" in result.search_text
    assert "ACC3M030" in result.search_text
    assert len(result.content_hash) == 64


def test_hash_is_deterministic():
    assert compute_hash("hola") == compute_hash("hola")
    assert compute_hash("hola") != compute_hash("Hola")