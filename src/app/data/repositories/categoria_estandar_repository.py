"""Consultas de CategoriaEstandar: la taxonomía global de siembra."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.categoria_estandar import CategoriaEstandar
from app.data.repositories.base_repository import BaseRepository


class CategoriaEstandarRepository(BaseRepository[CategoriaEstandar]):
    """Acceso a la taxonomía global -no filtra por usuario, es compartida."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, CategoriaEstandar)

    def listar_ordenadas(self) -> list[CategoriaEstandar]:
        return list(
            self.sesion.scalars(select(CategoriaEstandar).order_by(CategoriaEstandar.orden))
        )

    def buscar_por_codigo(self, codigo: str) -> CategoriaEstandar | None:
        return self.sesion.scalars(
            select(CategoriaEstandar).where(CategoriaEstandar.codigo == codigo)
        ).first()
