"""Consultas de ComercioCategoriaSugerida."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.comercio_categoria_sugerida import ComercioCategoriaSugerida
from app.data.repositories.base_repository import BaseRepository


class ComercioCategoriaRepository(BaseRepository[ComercioCategoriaSugerida]):
    """Acceso a las categorías que cada titular le asignó a sus comercios."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, ComercioCategoriaSugerida)

    def buscar(self, usuario_id: int, comercio_id: int) -> ComercioCategoriaSugerida | None:
        return self.sesion.scalars(
            select(ComercioCategoriaSugerida).where(
                ComercioCategoriaSugerida.usuario_id == usuario_id,
                ComercioCategoriaSugerida.comercio_id == comercio_id,
            )
        ).first()
