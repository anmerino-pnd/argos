CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- para typo tolerance / fuzzy
CREATE EXTENSION IF NOT EXISTS unaccent;         -- para búsqueda sin acentos

-- Configuración de full-text en español sin acentos
CREATE TEXT SEARCH CONFIGURATION es_unaccent ( COPY = spanish );
ALTER TEXT SEARCH CONFIGURATION es_unaccent
  ALTER MAPPING FOR hword, hword_part, word
  WITH unaccent, spanish_stem;

-- Verificación
DO $$
BEGIN
  RAISE NOTICE 'pgvector version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
END $$;