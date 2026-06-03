# ---- Stage 1: builder ----
FROM python:3.13-slim-bookworm AS builder

# uv binary
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Instalación de dependencias primero (capa cacheable)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Ahora el código fuente
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- Stage 2: runtime ----
FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

# Trae el venv ya construido
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# Usuario no-root por seguridad
RUN useradd -r -u 1000 -m argos && chown -R argos:argos /app
USER argos

EXPOSE 8000

# 2 workers de uvicorn. Cada uno es un proceso independiente con su propio
# pool de Postgres y caché de embeddings.
CMD ["uvicorn", "argos.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--access-log", \
     "--proxy-headers"]