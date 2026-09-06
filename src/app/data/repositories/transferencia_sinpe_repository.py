"""Consultas de TransferenciaSinpe: la caché local de transferencias SINPE ya parseadas."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.transferencia_sinpe import TransferenciaSinpe
from app.data.repositories.base_repository import BaseRepository


class TransferenciaSinpeRepository(BaseRepository[TransferenciaSinpe]):
    """Acceso a las transferencias SINPE ya sincronizadas de una cuenta de correo."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, TransferenciaSinpe)

    def listar_de_cuenta(self, cuenta_correo_id: int) -> list[TransferenciaSinpe]:
        """Todas las transferencias ya sincronizadas de un buzón."""
        return list(
            self.sesion.scalars(
                select(TransferenciaSinpe).where(
                    TransferenciaSinpe.cuenta_correo_id == cuenta_correo_id
                )
            )
        )

    def mensajes_ya_sincronizados(self, cuenta_correo_id: int, mensaje_ids: list[str]) -> set[str]:
        """De una lista de ids de mensaje, cuáles ya están guardados para esta cuenta.

        Misma base de sincronización incremental que `ComprobanteRepository`.
        """
        if not mensaje_ids:
            return set()
        filas = self.sesion.scalars(
            select(TransferenciaSinpe.mensaje_id).where(
                TransferenciaSinpe.cuenta_correo_id == cuenta_correo_id,
                TransferenciaSinpe.mensaje_id.in_(mensaje_ids),
            )
        )
        return set(filas)
