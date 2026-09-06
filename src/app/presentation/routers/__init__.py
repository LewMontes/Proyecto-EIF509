"""Routers de FastAPI: un archivo por area del dominio."""

from app.presentation.routers import categorias, compras, salud

__all__ = ["categorias", "compras", "salud"]
