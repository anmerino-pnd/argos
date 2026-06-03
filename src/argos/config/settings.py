"""Configuration centralizada. Lee del .env automáticamente."""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres
    database_url: str = Field(
        default="postgresql+asyncpg://argos:argos_dev@localhost:5432/argos"
    )

    # OpenAI
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 512
    embedding_batch_size: int = 100  # OpenAI permite hasta 2048, vamos conservadores

    # MySQL source
    mysql_host: str = ""
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_db: str = ""

    # Ingest
    ingest_batch_size: int = 500       # productos por página al leer de MySQL
    ingest_sample_limit: int | None = None  # si se setea, solo procesa N productos (para dev)


@lru_cache
def get_settings() -> Settings:
    return Settings()