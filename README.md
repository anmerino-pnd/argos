# Argos

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-0.8+-4169E1)](https://github.com/pgvector/pgvector)
[![OpenAI](https://img.shields.io/badge/OpenAI-embeddings-412991?logo=openai&logoColor=white)](https://platform.openai.com/docs/guides/embeddings)
[![Podman](https://img.shields.io/badge/Podman-rootless-892CA0?logo=podman&logoColor=white)](https://podman.io/)
[![uv](https://img.shields.io/badge/uv-package_manager-DE5FE9)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> Motor de búsqueda híbrido (léxico + semántico) para el catálogo de productos de CT Internacional. Sustituto autohospedado de Algolia con búsqueda vectorial nativa.

---

## ¿Qué es Argos?

Argos es una API de búsqueda construida sobre **PostgreSQL + pgvector**. Combina tres señales para producir resultados de alta calidad:

1. **Match exacto** en SKU (`clave`), número de parte (`numParte`), EAN y código SAT. Una clave exacta siempre va en el primer lugar.
2. **Búsqueda léxica** con `tsvector` en español sin acentos (para "cable utp", "3M pantalla", etc.).
3. **Búsqueda semántica** con embeddings de OpenAI (`text-embedding-3-small`, 512 dims) — permite encontrar productos por intención ("bobina de cable de red" → encuentra Cable UTP aunque no compartan palabras).

Las tres señales se fusionan con **Reciprocal Rank Fusion (RRF)** para producir un ranking unificado.

### ¿Por qué Argos sobre Algolia?

- **Costo**: cero costo de licencia. Solo embeddings de OpenAI (~$0.20 USD para ingestar todo el catálogo, centavos para mantenerlo).
- **Datos en casa**: el catálogo nunca sale de la infraestructura de CT.
- **Búsqueda semántica real**: vectores nativos de primera clase, no como add-on.
- **Especificidad de dominio**: sinónimos, boosts y reglas custom para términos técnicos de cómputo y telecomunicaciones.

---

## Arquitectura

```
┌────────────────┐         ┌──────────────────────────────────┐
│  Backend       │────────►│  Argos API (FastAPI + uvicorn)   │
│  página CT     │  HTTP   │  - Embedder (OpenAI, c/caché)    │
└────────────────┘         │  - SQL híbrido (tsvector+vector) │
                           └──────────────┬───────────────────┘
                                          │ asyncpg
                                          ▼
                           ┌──────────────────────────────────┐
                           │  PostgreSQL 16 + pgvector        │
                           │  - tabla productos (62k filas)   │
                           │  - HNSW index sobre embeddings   │
                           │  - GIN index sobre tsvector      │
                           └──────────────┬───────────────────┘
                                          ▲
                                          │ sync periódico (5 min)
                           ┌──────────────┴───────────────────┐
                           │  MySQL prod (catálogo CT)        │
                           └──────────────────────────────────┘
```

---

## Stack

- **Python 3.13** con `uv` para gestión de paquetes y entornos
- **FastAPI** + uvicorn (2 workers) para la API
- **PostgreSQL 16** + extensiones `vector`, `pg_trgm`, `unaccent`
- **OpenAI** `text-embedding-3-small` truncado a 512 dimensiones
- **Podman** rootless + Quadlet para orquestación de containers
- **AlmaLinux 9** como sistema operativo del server

---

## Requisitos

### Desarrollo local

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Podman 4.4+ o Docker (instalación local)
- Acceso a una API key de OpenAI

### Producción

- Server con Podman 5.x rootless, systemd 250+, AlmaLinux 9 o equivalente RHEL family
- Acceso de red al MySQL de producción
- 4 GB RAM libres, 5 GB disco
- API key de OpenAI con permisos para `text-embedding-3-small`

---

## Quick Start (local)

```bash
# 1. Clonar el repo
git clone <repo-url> argos
cd argos

# 2. Instalar dependencias con uv
uv sync

# 3. Configurar .env
cp .env.example .env
# Edita .env con tus credenciales (OPENAI_API_KEY, MySQL, password de Postgres)

# 4. Levantar Postgres con pgvector
podman compose up -d

# 5. Verificar extensiones
podman exec -it argos-postgres psql -U argos -d argos -c \
  "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector','pg_trgm','unaccent');"

# 6. Aplicar el schema
podman exec -i argos-postgres psql -U argos -d argos < migrations/001_init.sql

# 7. Ingest de prueba (limita a 200 productos primero)
echo "INGEST_SAMPLE_LIMIT=200" >> .env
uv run python scripts/run_ingest.py

# 8. Levantar la API
uv run uvicorn argos.main:app --reload --port 8000

# 9. Probar
curl "http://localhost:8000/search?q=cable+utp&limit=5"
```

Documentación interactiva de la API en `http://localhost:8000/docs` (Swagger).

---

## Despliegue en producción

Documentación completa: ver sección **[Despliegue](#despliegue-detallado)** abajo.

Resumen rápido:

```bash
# En el server, como tu usuario (NO root):
cd /opt   # o donde sea
git clone https://github.com/anmerino-pnd/argos argos
cd argos

# Build de la imagen
podman build -t argos:latest -f Containerfile .

# Configuración: ~/.config/argos/{postgres.env, argos.env}
# Quadlet units: ~/.config/containers/systemd/argos*.{network,volume,container}

# Persistencia de servicios usuario en boot
sudo loginctl enable-linger $USER

# Activar
systemctl --user daemon-reload
systemctl --user start argos-postgres.service
podman exec -i argos-postgres psql -U argos -d argos < migrations/001_init.sql
podman run --rm --network=host --env-file=$HOME/.config/argos/argos.env \
  localhost/argos:latest python scripts/run_ingest.py
systemctl --user start argos-api.service
```

---

## Configuración

### Variables de entorno

| Variable                 | Default                    | Descripción                                                             |
| ------------------------ | -------------------------- | ------------------------------------------------------------------------ |
| `DATABASE_URL`         | (requerido)                | URL de Postgres. Formato:`postgresql+asyncpg://user:pass@host:5432/db` |
| `OPENAI_API_KEY`       | (requerido)                | API key de OpenAI                                                        |
| `EMBEDDING_MODEL`      | `text-embedding-3-small` | Modelo de OpenAI para embeddings                                         |
| `EMBEDDING_DIMENSIONS` | `512`                    | Dimensiones del vector (debe coincidir con la columna en Postgres)       |
| `EMBEDDING_BATCH_SIZE` | `100`                    | Productos por batch al embeber                                           |
| `MYSQL_HOST`           | (requerido para ingest)    | Host del MySQL fuente                                                    |
| `MYSQL_PORT`           | `3306`                   | Puerto MySQL                                                             |
| `MYSQL_USER`           | (requerido)                | Usuario MySQL (idealmente read-only)                                     |
| `MYSQL_PASSWORD`       | (requerido)                | Password MySQL —**sin comillas**                                  |
| `MYSQL_DB`             | (requerido)                | Nombre de la base de datos                                               |
| `INGEST_BATCH_SIZE`    | `500`                    | Productos por página al leer de MySQL                                   |
| `INGEST_SAMPLE_LIMIT`  | (vacío)                   | Si se setea, el ingest solo procesa N productos. Útil para testing.     |

> ⚠️ **No uses comillas** alrededor de los valores en `.env`. `MYSQL_PASSWORD="abc"` interpreta las comillas como parte del password. Escribe `MYSQL_PASSWORD=abc`.

---

## API

### Endpoints

| Método  | Ruta                                | Descripción                             |
| -------- | ----------------------------------- | ---------------------------------------- |
| `GET`  | `/health`                         | Liveness check                           |
| `GET`  | `/stats`                          | Estadísticas de la caché de embeddings |
| `GET`  | `/search?q=...&limit=20&offset=0` | Búsqueda (querystring)                  |
| `POST` | `/search`                         | Búsqueda (JSON body)                    |
| `GET`  | `/docs`                           | Swagger UI interactivo                   |

### Ejemplo de request

```bash
curl "http://localhost:8088/search?q=cable+utp&limit=5"
```

### Ejemplo de response

```json
{
  "query": "cable utp",
  "took_ms": 47,
  "total": 5,
  "cached": true,
  "results": [
    {
      "id_producto": 131,
      "clave": "ACCCDM1000",
      "modelo": "66445872",
      "tipo": "Cable UTP",
      "marca_nombre": "CONDUMEX",
      "categoria_nombre": "Bobinas",
      "descripcion_corta": "66445872 CABLE UTP ULTRACAT 5E 305M AMAR",
      "score": 0.0311
    }
  ]
}
```

---

## Despliegue detallado

### Estructura de directorios en el server

```
~/argos/                              # repo clonado
~/.config/argos/                      # config y secretos
  ├── postgres.env
  └── argos.env
~/.config/containers/systemd/         # Quadlet (systemd-user)
  ├── argos.network
  ├── argos-pgdata.volume
  ├── argos-postgres.container
  └── argos-api.container
```

### Comandos operativos comunes

```bash
# Estado de servicios
systemctl --user status argos-postgres.service argos-api.service

# Logs en tiempo real
podman logs -f argos-api
podman logs -f argos-postgres

# Reiniciar API después de un deploy
systemctl --user restart argos-api.service

# Sync manual del catálogo (one-shot)
podman run --rm --network=host \
  --env-file=$HOME/.config/argos/argos.env \
  localhost/argos:latest \
  python scripts/run_ingest.py

# Conectarse a Postgres con psql
podman exec -it argos-postgres psql -U argos -d argos

# Métricas rápidas del catálogo
podman exec -it argos-postgres psql -U argos -d argos -c "
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE activo) AS activos,
       COUNT(embedding) AS con_embedding,
       MAX(updated_at) AS ultimo_update
FROM productos;"
```

### Actualizar la imagen después de cambios en el código

```bash
cd ~/argos
git pull
podman build --no-cache -t argos:latest -f Containerfile .
systemctl --user restart argos-api.service
```

---

## Sync automático (systemd timer)

El catálogo se re-sincroniza cada **5 minutos** vía un timer de systemd. La lógica:

1. Lee todos los IDs activos de MySQL (`SELECT idProductos FROM productos WHERE activo = 1`).
2. Compara con los IDs en Postgres. Los que ya no aparecen en MySQL se marcan como `activo = false` en Argos (soft-delete).
3. Los productos cuyo `content_hash` cambió se re-embeben.
4. Los productos nuevos se insertan y embeben.

Costo: típicamente $0.001-0.01 USD por ciclo (solo embebe los cambios). El UPSERT usa el `content_hash` para no llamar a OpenAI sin necesidad.

Estado del timer:

```bash
systemctl --user list-timers argos-sync.timer
journalctl --user -u argos-sync.service --since "1 hour ago"
```

---

## Estructura del proyecto

```
argos/
├── src/argos/
│   ├── main.py                # entrada de FastAPI
│   ├── config/                # settings (Pydantic)
│   ├── db/                    # conexión asyncpg + pool
│   ├── ingest/
│   │   ├── mysql_source.py    # lectura paginada de MySQL
│   │   ├── transform.py       # build search_text + hash
│   │   ├── embed.py           # cliente OpenAI con caché
│   │   ├── upsert.py          # UPSERT en Postgres
│   │   └── pipeline.py        # orquestador del ingest
│   └── search/
│       ├── hybrid.py          # SQL híbrido + RRF
│       └── schemas.py         # Pydantic request/response
├── migrations/                # SQL plano, numerado
├── scripts/
│   ├── run_ingest.py          # CLI para el ingest
│   └── init.sql               # init de Postgres
├── tests/
├── pyproject.toml             # deps gestionadas con uv
├── Containerfile              # imagen de producción
├── compose.yaml               # desarrollo local
└── README.md
```

---

## Desarrollo

### Tests

```bash
uv run pytest tests/ -v
```

### Lint y formato

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Probar búsqueda sin levantar la API

```bash
uv run python scripts/search_cli.py "cable utp" 10
```

### Construir imagen local

```bash
podman build -t argos:latest -f Containerfile .
```

---

## Troubleshooting

### El ingest truena con "Access denied for user"

MySQL ve una IP de origen distinta a la que tienes whitelisted. Verifica:

- Si Argos corre dentro de container con red bridge, MySQL ve la IP NAT del container, no la del host. Solución: usar `Network=host` en los Quadlet/compose, o pedir whitelist de la IP del container.
- Si la password tiene caracteres especiales (`!`, `$`, etc.), **no la pongas con comillas** en el `.env`.

### La API truena con `ModuleNotFoundError: No module named 'argos.api'`

El `CMD` del `Containerfile` debe apuntar a `argos.main:app` (no `argos.api.main:app`). Verifica:

```bash
grep CMD Containerfile
```

### El ingest no encuentra `scripts/run_ingest.py`

`scripts/` debe estar copiado al container. Verifica el `Containerfile` tenga `COPY scripts/ ./scripts/` y que `scripts/` **no esté** en `.containerignore`.

### Búsquedas devuelven 0 resultados

Verifica que la tabla tenga datos y embeddings:

```bash
podman exec -it argos-postgres psql -U argos -d argos -c \
  "SELECT COUNT(*), COUNT(embedding) FROM productos WHERE activo;"
```

Si `COUNT(embedding)` es 0, falta correr el ingest.

### El API arranca pero no responde

Probablemente está en `Network=host` y el `--port` no coincide con el del Quadlet. Verifica:

```bash
ss -tlnp | grep 8088
```

---

## Roadmap

- [X] Búsqueda híbrida (léxico + semántico + match exacto)
- [X] Caché de embeddings de queries
- [X] Paginación con `limit` y `offset`
- [X] Filtro automático por `activo`
- [X] Despliegue con Podman + Quadlet
- [ ] Sync automático cada 5 min con detección de borrados (**en desarrollo**)
- [ ] Filtros por categoría y marca (con conteos/facets)
- [ ] Sinónimos y tolerancia a typos (`pg_trgm`)
- [ ] Tabla `argos_search_log` para observabilidad
- [ ] Documentación completa con Quarto
- [ ] Filtros estructurados de Icecat (Tipo, Color, Longitud, etc.)
- [ ] Reverse proxy con Apache + TLS
- [ ] Modo shadow contra Algolia

---

## Licencia

MIT — ver [LICENSE](LICENSE).

## Autor

**Angel Merino** · CT Internacional · [acedeno00@gmail.com](mailto:acedeno00@gmail.com)
