"""Consultas de MetodoPago."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.metodo_pago import MetodoPago
from app.data.repositories.base_repository import BaseRepository


class MetodoPagoRepository(BaseRepository[MetodoPago]):
    """Acceso a los métodos de pago de un titular."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, MetodoPago)

    def buscar_por_ultimos_cuatro(self, usuario_id: int, ultimos_cuatro: str) -> MetodoPago | None:
        """El emparejamiento real de la ingesta: dado el titular y los cuatro
        dígitos que trajo el correo, encontrar su tarjeta activa."""
        return self.sesion.scalars(
            select(MetodoPago).where(
                MetodoPago.usuario_id == usuario_id,
                MetodoPago.ultimos_cuatro == ultimos_cuatro,
                MetodoPago.activo.is_(True),
            )
        ).first()

    def listar_de_usuario(self, usuario_id: int) -> list[MetodoPago]:
        return list(
            self.sesion.scalars(
                select(MetodoPago)
                .where(MetodoPago.usuario_id == usuario_id)
                .order_by(MetodoPago.alias)
            )
        )

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> MetodoPago | None:
        return self.sesion.scalars(
            select(MetodoPago).where(
                MetodoPago.id == identificador, MetodoPago.usuario_id == usuario_id
            )
        ).first()

    def buscar_por_alias(self, usuario_id: int, alias: str) -> MetodoPago | None:
        return self.sesion.scalars(
            select(MetodoPago).where(
                MetodoPago.usuario_id == usuario_id, MetodoPago.alias.ilike(alias)
            )
        ).first()
