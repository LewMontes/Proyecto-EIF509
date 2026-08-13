"""Configuracion de la aplicacion.

Todo valor que cambie entre maquinas (URL de la base, modo debug) se lee de
variables de entorno o del archivo .env. Nunca se escribe a mano en el codigo.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_nombre: str = "Gastonomo"
    app_version: str = "0.1.0"
    debug: bool = False

    # SQLite local para el Laboratorio 1: el esqueleto arranca y funciona completo
    # sin pedirle a nadie que instale un servidor de base de datos. El paso a
    # PostgreSQL llega en proximos laboratorios y solo requiere cambiar esta URL
    # (ver ADR-001).
    database_url: str = "sqlite:///./gastonomo.db"

    # Moneda base del sistema: todo monto se convierte tambien a esta para poder
    # sumar compras hechas en dolares junto con las hechas en colones.
    moneda_base: str = "CRC"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuracion. Se cachea para no releer el .env en cada request."""
    return Settings()
