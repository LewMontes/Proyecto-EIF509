"""Entidad Presupuesto: el tope de gasto de una categoría para un mes."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base
from app.data.models.enums import Moneda

if TYPE_CHECKING:
    from app.data.models.categoria import Categoria
    from app.data.models.usuario import Usuario


class Presupuesto(Base):
    """Tope de gasto de una categoría de un titular en un año y mes concretos.

    `monto_consumido` se acumula dentro de la misma transacción que registra
    cada compra (`ConciliacionService`), no se recalcula en cada consulta: el
    frontend lo muestra en vivo, y recalcular la suma de todas las compras
    del mes en cada refresco de pantalla no escala. Anular una compra
    devuelve su monto -nunca queda negativo.
    """

    __tablename__ = "presupuesto"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id",
            "categoria_id",
            "anio",
            "mes",
            name="uq_presupuesto_usuario_categoria_periodo",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categoria.id"), nullable=False, index=True
    )
    anio: Mapped[int] = mapped_column(nullable=False)
    mes: Mapped[int] = mapped_column(nullable=False)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda), nullable=False)
    monto_limite: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    monto_consumido: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    umbral_alerta: Mapped[int] = mapped_column(nullable=False, default=80)

    usuario: Mapped["Usuario"] = relationship(back_populates="presupuestos", lazy="select")
    categoria: Mapped["Categoria"] = relationship(back_populates="presupuestos", lazy="select")

    def __repr__(self) -> str:
        return (
            f"Presupuesto(usuario_id={self.usuario_id!r}, categoria_id={self.categoria_id!r}, "
            f"{self.anio}-{self.mes:02d})"
        )
