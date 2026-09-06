"""Entidad TipoCambio: histórico de tasas por fecha.

`TipoCambioService` (business/services/tipo_cambio_service.py) consulta el
BCCR/Hacienda con una caché en memoria de proceso -no persiste nada, es un
dato público de referencia-. Esta tabla es otra cosa: el registro de qué
tasa se aplicó *de verdad* a cada compra convertida, para poder responder
"con qué tasa se convirtió esto" sin depender de que la caché en memoria
siga viva. `ConciliacionService` la llena, no `TipoCambioService`.

No tiene llave foránea desde `Compra` a propósito: la compra guarda copiada
la tasa que se le aplicó (`Compra.tipo_cambio_aplicado`), no una referencia.
Si apuntara a esta fila, corregir una tasa mal cargada cambiaría
retroactivamente los totales de compras ya cerradas.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Enum, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.models.base import Base
from app.data.models.enums import Moneda


class TipoCambio(Base):
    """Una tasa de conversión de una moneda a otra, para una fecha concreta."""

    __tablename__ = "tipo_cambio"
    __table_args__ = (
        UniqueConstraint(
            "moneda_origen", "moneda_destino", "fecha", name="uq_tipo_cambio_par_fecha"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    moneda_origen: Mapped[Moneda] = mapped_column(Enum(Moneda), nullable=False)
    moneda_destino: Mapped[Moneda] = mapped_column(Enum(Moneda), nullable=False)
    fecha: Mapped[date] = mapped_column(nullable=False, index=True)
    tasa: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    fuente: Mapped[str] = mapped_column(String(60), nullable=False, default="BCCR")

    def __repr__(self) -> str:
        return (
            f"TipoCambio({self.moneda_origen}->{self.moneda_destino}, "
            f"{self.fecha}, tasa={self.tasa!r})"
        )
