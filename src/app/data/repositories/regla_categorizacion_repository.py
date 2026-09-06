"""Consultas de ReglaCategorizacion."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.repositories.base_repository import BaseRepository


class ReglaCategorizacionRepository(BaseRepository[ReglaCategorizacion]):
    """Acceso a las reglas de categorización de un titular."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, ReglaCategorizacion)

    def listar_activas_ordenadas(self, usuario_id: int) -> list[ReglaCategorizacion]:
        """Las reglas activas de este titular, en orden de prioridad ascendente
        -es el recorrido exacto del motor: gana la primera que coincide."""
        return list(
            self.sesion.scalars(
                select(ReglaCategorizacion)
                .where(
                    ReglaCategorizacion.usuario_id == usuario_id,
                    ReglaCategorizacion.activa.is_(True),
                )
                .order_by(ReglaCategorizacion.prioridad)
            )
        )

    def listar_de_usuario(self, usuario_id: int) -> list[ReglaCategorizacion]:
        return list(
            self.sesion.scalars(
                select(ReglaCategorizacion)
                .where(ReglaCategorizacion.usuario_id == usuario_id)
                .order_by(ReglaCategorizacion.prioridad)
            )
        )

    def buscar_por_nombre(self, usuario_id: int, nombre: str) -> ReglaCategorizacion | None:
        return self.sesion.scalars(
            select(ReglaCategorizacion).where(
                ReglaCategorizacion.usuario_id == usuario_id,
                ReglaCategorizacion.nombre.ilike(nombre),
            )
        ).first()

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> ReglaCategorizacion | None:
        return self.sesion.scalars(
            select(ReglaCategorizacion).where(
                ReglaCategorizacion.id == identificador,
                ReglaCategorizacion.usuario_id == usuario_id,
            )
        ).first()

    def buscar_por_prioridad(self, usuario_id: int, prioridad: int) -> ReglaCategorizacion | None:
        return self.sesion.scalars(
            select(ReglaCategorizacion).where(
                ReglaCategorizacion.usuario_id == usuario_id,
                ReglaCategorizacion.prioridad == prioridad,
            )
        ).first()

    def prioridad_siguiente(self, usuario_id: int) -> int:
        """La próxima prioridad libre -uno más que la mayor que ya tenga el titular."""
        maxima = self.sesion.scalar(
            select(ReglaCategorizacion.prioridad)
            .where(ReglaCategorizacion.usuario_id == usuario_id)
            .order_by(ReglaCategorizacion.prioridad.desc())
            .limit(1)
        )
        return (maxima or 0) + 1
