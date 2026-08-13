"""Routers de FastAPI: un archivo por area del dominio."""

from app.presentation.routers import categorias, salud

__all__ = ["categorias", "salud"]
