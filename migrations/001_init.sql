-- =========================
-- Tabla principal: productos
-- =========================
CREATE TABLE productos (
    id_producto       INTEGER     PRIMARY KEY,

    -- Identificadores (matches exactos, alta prioridad en ranking)
    clave             VARCHAR(10) NOT NULL,
    num_parte         VARCHAR(64),
    ean               VARCHAR(100),
    codigo_sat        VARCHAR(20),

    -- Atributos para mostrar y filtrar
    modelo            VARCHAR(100),
    tipo              VARCHAR(45),
    descripcion_corta VARCHAR(255),
    descripcion       TEXT,
    palabras_clave    TEXT,

    -- Relaciones denormalizadas (nombre legible, no solo el ID)
    id_categoria      INTEGER     NOT NULL,
    categoria_nombre  VARCHAR(255),
    id_marca          INTEGER     NOT NULL,
    marca_nombre      VARCHAR(255),

    -- Estado
    activo            BOOLEAN     NOT NULL DEFAULT TRUE,

    -- Búsqueda
    search_text       TEXT        NOT NULL,        -- texto curado: lo que se embebe y se indexa
    search_tsv        tsvector,                    -- full-text index, lo llena el ingest
    embedding         vector(512),                 -- nullable hasta primera generación

    -- Control de embeddings (evita re-embeber sin cambios)
    content_hash      CHAR(64)    NOT NULL,        -- sha256(search_text)
    embedded_at       TIMESTAMPTZ,
    embedding_model   VARCHAR(50),

    -- Auditoría
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =========================
-- Índices
-- =========================

-- Full-text search en español sin acentos
CREATE INDEX productos_search_tsv_idx
    ON productos USING GIN (search_tsv);

-- Búsqueda vectorial (HNSW; solo filas con embedding)
CREATE INDEX productos_embedding_hnsw
    ON productos USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Matches exactos
CREATE INDEX productos_clave_idx        ON productos (clave);
CREATE INDEX productos_ean_idx          ON productos (ean) WHERE ean <> '';
CREATE INDEX productos_codigo_sat_idx   ON productos (codigo_sat) WHERE codigo_sat IS NOT NULL;

-- Búsqueda fuzzy en número de parte (typo tolerance en SKUs/modelos)
CREATE INDEX productos_num_parte_trgm
    ON productos USING GIN (num_parte gin_trgm_ops);
CREATE INDEX productos_modelo_trgm
    ON productos USING GIN (modelo gin_trgm_ops);

-- Filtros
CREATE INDEX productos_activo_idx    ON productos (activo) WHERE activo = TRUE;
CREATE INDEX productos_categoria_idx ON productos (id_categoria);
CREATE INDEX productos_marca_idx     ON productos (id_marca);

-- =========================
-- Trigger para updated_at
-- =========================
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER productos_set_updated_at
    BEFORE UPDATE ON productos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();