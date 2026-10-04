"""Consultas de Comprobante: la caché local de mensajes de BAC ya parseados."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.comprobante import Comprobante
from app.data.models.enums import EstadoComprobante
from app.data.paginacion import Pagina, SolicitudDePagina, paginar
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

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> Comprobante | None:
        """El comprobante, solo si pertenece al titular indicado."""
        return self.sesion.scalars(
            select(Comprobante).where(
                Comprobante.id == identificador, Comprobante.usuario_id == usuario_id
            )
        ).first()

    def buscar_por_mensaje(self, cuenta_correo_id: int, mensaje_id: str) -> Comprobante | None:
        """El comprobante que ya se recibió para ese mensaje de ese buzón, si existe.

        Es la consulta de la idempotencia: si el buzón reentrega el mismo
        correo, esto lo encuentra y la ingesta lo rechaza en vez de duplicar
        el gasto.
        """
        return self.sesion.scalars(
            select(Comprobante).where(
                Comprobante.cuenta_correo_id == cuenta_correo_id,
                Comprobante.mensaje_id == mensaje_id,
            )
        ).first()

    COLUMNAS_ORDENABLES = {
        "recibido_en": Comprobante.recibido_en,
        "fecha": Comprobante.fecha,
        "monto": Comprobante.monto,
        "id": Comprobante.id,
    }

    def paginar_de_usuario(
        self,
        usuario_id: int,
        estado: EstadoComprobante | None,
        solicitud: SolicitudDePagina,
    ) -> Pagina[Comprobante]:
        """Una página de los comprobantes del titular, opcionalmente de un solo estado."""
        consulta = select(Comprobante).where(Comprobante.usuario_id == usuario_id)
        if estado is not None:
            consulta = consulta.where(Comprobante.estado == estado)
        return paginar(
            self.sesion,
            consulta,
            solicitud,
            self.COLUMNAS_ORDENABLES,
            desempate=Comprobante.id.desc(),
        )
