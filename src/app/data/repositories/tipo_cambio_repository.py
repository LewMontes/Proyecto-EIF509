"""Consultas de TipoCambio: el histórico de tasas por fecha."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.enums import Moneda
from app.data.models.tipo_cambio import TipoCambio
from app.data.repositories.base_repository import BaseRepository


class TipoCambioRepository(BaseRepository[TipoCambio]):
    """Acceso al histórico de tipos de cambio."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, TipoCambio)

    def buscar(
        self, moneda_origen: Moneda, moneda_destino: Moneda, fecha: date
    ) -> TipoCambio | None:
        return self.sesion.scalars(
            select(TipoCambio).where(
                TipoCambio.moneda_origen == moneda_origen,
                TipoCambio.moneda_destino == moneda_destino,
                TipoCambio.fecha == fecha,
            )
        ).first()

    def guardar_tasa(
        self, moneda_origen: Moneda, moneda_destino: Moneda, fecha: date, tasa, fuente: str
    ) -> TipoCambio:
        """Registra la tasa aplicada ese día, o la deja igual si ya estaba -no
        pisa un valor ya guardado con uno recién consultado que podría venir
        de una segunda llamada al mismo proveedor en el mismo día."""
        existente = self.buscar(moneda_origen, moneda_destino, fecha)
        if existente is not None:
            return existente
        fila = TipoCambio(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            fecha=fecha,
            tasa=tasa,
            fuente=fuente,
        )
        return self.agregar(fila)
