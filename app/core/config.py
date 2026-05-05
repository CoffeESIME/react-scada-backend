"""
Configuración global del sistema usando Pydantic Settings (Twelve-Factor App).

Carga variables de entorno desde .env y valida coherencia del entorno
de despliegue (VPS_LOCAL | EDGE_PLANTA | DEVELOPMENT).
"""
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentEnv(str, Enum):
    """Entornos de despliegue soportados."""
    VPS_LOCAL   = "vps_local"    
    EDGE_PLANTA = "edge_planta"  
    DEVELOPMENT = "development"  


class Settings(BaseSettings):
    """
    Configuración principal del backend SCADA.

    Todas las variables de entorno sensibles se leen desde el archivo
    .env correspondiente al entorno de despliegue; nunca se hardcodean.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    
    
    
    app_name: str = "SCADA Backend"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    
    deployment_env: DeploymentEnv = DeploymentEnv.DEVELOPMENT

    
    
    
    postgres_user: str = "admin"
    postgres_password: str = "admin_scada_secret"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "scada_system"

    @property
    def database_url(self) -> str:
        """URL de conexión async para SQLAlchemy (psycopg3)."""
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

    
    
    
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_client_id: str = "scada-backend"

    
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None

    
    mqtt_keepalive: int = 60          
    mqtt_reconnect_delay: float = 5.0  

    
    
    
    
    mqtt_use_tls: bool = False

    
    
    mqtt_ca_cert: Optional[Path] = None

    
    mqtt_client_cert: Optional[Path] = None

    
    mqtt_client_key: Optional[Path] = None

    
    
    
    secret_key: str = "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    
    
    
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    
    
    

    @field_validator("mqtt_ca_cert", "mqtt_client_cert", "mqtt_client_key", mode="before")
    @classmethod
    def _coerce_path(cls, v: Optional[str]) -> Optional[Path]:
        """Convierte strings vacíos a None para evitar rutas fantasma."""
        if v in (None, "", "null", "none"):
            return None
        return Path(v)

    @model_validator(mode="after")
    def _validate_tls_coherence(self) -> "Settings":
        """
        Garantiza que los archivos de certificado existen cuando TLS está activo,
        y que edge_planta nunca arranque sin mTLS (fail-fast en producción).
        """
        if self.deployment_env == DeploymentEnv.EDGE_PLANTA:
            
            object.__setattr__(self, "mqtt_use_tls", True)

            missing: list[str] = []
            for attr, label in [
                ("mqtt_ca_cert",     "MQTT_CA_CERT"),
                ("mqtt_client_cert", "MQTT_CLIENT_CERT"),
                ("mqtt_client_key",  "MQTT_CLIENT_KEY"),
            ]:
                path: Optional[Path] = getattr(self, attr)
                if path is None:
                    missing.append(label)
                elif not path.exists():
                    raise ValueError(
                        f"[EDGE_PLANTA] El certificado '{label}' no existe en la ruta: {path}"
                    )
            if missing:
                raise ValueError(
                    f"[EDGE_PLANTA] mTLS requiere los siguientes certificados: {', '.join(missing)}"
                )

        if self.mqtt_use_tls and self.mqtt_ca_cert:
            if not self.mqtt_ca_cert.exists():
                raise ValueError(
                    f"MQTT_CA_CERT apunta a una ruta inexistente: {self.mqtt_ca_cert}"
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración (singleton thread-safe)."""
    return Settings()



settings = get_settings()
