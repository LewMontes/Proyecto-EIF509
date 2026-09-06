"""Consultas de Presupuesto."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.presupuesto import Presupuesto
from app.data.repositories.base_repository import BaseRepository


class PresupuestoRepository(BaseRepository[Presupuesto]):
    """Acceso a los presupuestos de un titular."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Presupuesto)

    def buscar(self, usuario_id: int, categoria_id: int, anio: int, mes: int) -> Presupuesto | None:
        return self.sesion.scalars(
            select(Presupuesto).where(
                Presupuesto.usuario_id == usuario_id,
                Presupuesto.categoria_id == categoria_id,
                Presupuesto.anio == anio,
                Presupuesto.mes == mes,
            )
        ).first()

    def listar_del_periodo(self, usuario_id: int, anio: int, mes: int) -> list[Presupuesto]:
        return list(
            self.sesion.scalars(
                select(Presupuesto).where(
                    Presupuesto.usuario_id == usuario_id,
                    Presupuesto.anio == anio,
                    Presupuesto.mes == mes,
                )
            )
        )

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> Presupuesto | None:
        """Obtiene un presupuesto solo si pertenece al titular indicado."""
        return self.sesion.scalars(
            select(Presupuesto).where(
                Presupuesto.id == identificador,
                Presupuesto.usuario_id == usuario_id,
            )
        ).first()
