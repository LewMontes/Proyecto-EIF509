"""Entidad TransferenciaSinpe: el resultado ya parseado de una notificación de SINPE recibida.

Mismo motivo que `Comprobante`: cachear el resultado de `parsear_transferencia_sinpe`
por mensaje, para no tener que volver a pedirle el cuerpo al proveedor de correo
cada vez que se abre la pantalla de SINPE. `mensaje_id` es la misma clave de
deduplicación.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base

if TYPE_CHECKING:
    from app.data.models.cuenta_correo import CuentaCorreo


class TransferenciaSinpe(Base):
    """Una notificación de SINPE recibida, ya leída y parseada.

    Es un espejo de `TransferenciaSinpeParseada` -el mismo resultado de
    lectura, ahora persistido- no una entidad de negocio nueva, igual que
    `Comprobante` respecto de `ComprobanteParseado`.
    """

    __tablename__ = "transferencia_sinpe"
    __table_args__ = (
        UniqueConstraint(
            "cuenta_correo_id", "mensaje_id", name="uq_transferencia_sinpe_cuenta_mensaje"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_correo_id: Mapped[int] = mapped_column(
        ForeignKey("cuenta_correo.id"), nullable=False, index=True
    )
    mensaje_id: Mapped[str] = mapped_column(String(300), nullable=False)

    banco: Mapped[str] = mapped_column(String(80), nullable=False)
    destinatario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cuenta_destino: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Naive a propósito, igual que Comprobante.fecha: es la hora local de
    # Costa Rica que el banco escribe en la notificación, sin zona horaria.
    fecha: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    moneda: Mapped[str | None] = mapped_column(String(3), nullable=True)
    monto: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    concepto: Mapped[str | None] = mapped_column(String(300), nullable=True)
    referencia: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Solo el Banco Nacional lo incluye en su notificación; BAC no.
    comprobante: Mapped[str | None] = mapped_column(String(60), nullable=True)
    confianza: Mapped[float] = mapped_column(nullable=False)
    # False si salió del lector genérico (`transferencia_sinpe.py`), no de un
    # lector validado contra una notificación real de ese banco.
    confirmado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    cuenta_correo: Mapped["CuentaCorreo"] = relationship(
        back_populates="transferencias_sinpe", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"TransferenciaSinpe(cuenta_correo_id={self.cuenta_correo_id!r}, "
            f"mensaje_id={self.mensaje_id!r}, banco={self.banco!r})"
        )
