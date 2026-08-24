"""Repositorios: el unico lugar del sistema que sabe como se consultan los datos."""

from app.data.repositories.base_repository import BaseRepository
from app.data.repositories.categoria_repository import CategoriaRepository

__all__ = [
    "BaseRepository",
    "CategoriaRepository",
]
