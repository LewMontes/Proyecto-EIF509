"""Entidad LineaCompra: un renglón de una compra, con su propia categoría.

Una compra ingerida por correo nace con un único renglón por el monto total
-el comprobante solo trae el total, nunca el detalle de qué se compró-; el
desglose en varios renglones es un refinamiento manual que todavía no tiene
UI (ver el plan de esta ronda).
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base

if TYPE_CHECKING:
    from app.data.models.categoria import Categoria
    from app.data.models.compra import Compra


class LineaCompra(Base):
    """Renglón de una compra. No tiene existencia fuera de su compra."""

    __tablename__ = "linea_compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(
        ForeignKey("compra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"), nullable=True)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=1)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    descuento: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    exento_impuesto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    categorizada_automaticamente: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    compra: Mapped["Compra"] = relationship(back_populates="lineas", lazy="select")
    # Nula mientras la conciliacion no logro clasificar el renglon: la compra
    # se guarda igual, marcada `requiere_revision`.
    categoria: Mapped[Optional["Categoria"]] = relationship(back_populates="lineas", lazy="select")

    def __repr__(self) -> str:
        return f"LineaCompra(compra_id={self.compra_id!r}, descripcion={self.descripcion!r})"
