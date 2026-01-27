"""
Configuración global del sistema usando Pydantic Settings.
Carga variables de entorno desde .env
"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración principal del backend SCADA."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # === App ===
    app_name: str = "SCADA Backend"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    
    # === Database (TimescaleDB/PostgreSQL) ===
    postgres_user: str = "admin"
    postgres_password: str = "admin_scada_secret"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "scada_system"
    
    @property
    def database_url(self) -> str:
        """URL de conexión async para SQLAlchemy."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def database_url_sync(self) -> str:
        """URL de conexión sync para Alembic."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    # === MQTT (Mosquitto) ===
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_client_id: str = "scada-backend"
    
    # === Security ===
    secret_key: str = "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # === CORS ===
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración."""
    return Settings()


# Singleton para uso directo
settings = get_settings()
