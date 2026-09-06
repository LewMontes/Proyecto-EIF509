"""Consultas de Comprobante: la caché local de mensajes de BAC ya parseados."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.comprobante import Comprobante
from app.data.repositories.base_repository import BaseRepository


class ComprobanteRepository(BaseRepository[Comprobante]):
    """Acceso a los comprobantes ya sincronizados de una cuenta de correo."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Comprobante)

    def listar_de_cuenta(self, cuenta_correo_id: int) -> list[Comprobante]:
        """Todos los comprobantes ya sincronizados de un buzón, sin filtrar por período."""
        return list(
            self.sesion.scalars(
                select(Comprobante).where(Comprobante.cuenta_correo_id == cuenta_correo_id)
            )
        )

    def mensajes_ya_sincronizados(self, cuenta_correo_id: int, mensaje_ids: list[str]) -> set[str]:
        """De una lista de ids de mensaje, cuáles ya están guardados para esta cuenta.

        Es la base de la sincronización incremental: `sincronizar` solo pide el
        cuerpo y parsea los mensajes que este método no devuelve.
        """
        if not mensaje_ids:
            return set()
        filas = self.sesion.scalars(
            select(Comprobante.mensaje_id).where(
                Comprobante.cuenta_correo_id == cuenta_correo_id,
                Comprobante.mensaje_id.in_(mensaje_ids),
            )
        )
        return set(filas)
