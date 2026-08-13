"""Consultas sobre categorias."""

from __future__ import annotations

from sqlalchemy import select

from app.data.models.categoria import Categoria
from app.data.repositories.base_repository import BaseRepository


class CategoriaRepository(BaseRepository[Categoria]):
    modelo = Categoria

    def listar_por_usuario(
        self, usuario_id: int, incluir_inactivas: bool = False
    ) -> list[Categoria]:
        sentencia = select(Categoria).where(Categoria.usuario_id == usuario_id)
        if not incluir_inactivas:
            sentencia = sentencia.where(Categoria.activa.is_(True))
        return list(self.session.scalars(sentencia.order_by(Categoria.nombre)))

    def buscar_por_nombre(self, usuario_id: int, nombre: str) -> Categoria | None:
        """Busca por nombre exacto. Lo usa la validacion de nombre unico."""
        sentencia = select(Categoria).where(
            Categoria.usuario_id == usuario_id,
            Categoria.nombre == nombre,
        )
        return self.session.scalars(sentencia).one_or_none()
