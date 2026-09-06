"""Consultas de Comercio."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.comercio import Comercio
from app.data.repositories.base_repository import BaseRepository


class ComercioRepository(BaseRepository[Comercio]):
    """Acceso al catálogo compartido de comercios."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Comercio)

    def buscar_por_nombre_normalizado(self, nombre_normalizado: str) -> Comercio | None:
        return self.sesion.scalars(
            select(Comercio).where(Comercio.nombre_normalizado == nombre_normalizado)
        ).first()
