"""Consultas de Categoria.

Todas reciben `usuario_id` y filtran por el. El aislamiento entre cuentas se
sostiene aqui: si una consulta olvidara el filtro, ninguna capa de arriba podria
darse cuenta.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.categoria import Categoria
from app.data.repositories.base_repository import BaseRepository


class CategoriaRepository(BaseRepository[Categoria]):
    """Acceso a las categorias de un usuario."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Categoria)

    def buscar_por_nombre(self, usuario_id: int, nombre: str) -> Categoria | None:
        """Busca por nombre exacto dentro de la cuenta, sin distinguir mayusculas."""
        return self.sesion.scalars(
            select(Categoria).where(
                Categoria.usuario_id == usuario_id,
                Categoria.nombre.ilike(nombre),
            )
        ).first()

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> Categoria | None:
        """Obtiene una categoria solo si pertenece a la cuenta indicada.

        Es la consulta que impide que alguien manipule datos de otra cuenta
        pasando un id ajeno como categoria padre.
        """
        return self.sesion.scalars(
            select(Categoria).where(
                Categoria.id == identificador,
                Categoria.usuario_id == usuario_id,
            )
        ).first()

    def listar_activas_de_usuario(self, usuario_id: int) -> list[Categoria]:
        return list(
            self.sesion.scalars(
                select(Categoria)
                .where(Categoria.usuario_id == usuario_id, Categoria.activa.is_(True))
                .order_by(Categoria.nombre)
            )
        )
