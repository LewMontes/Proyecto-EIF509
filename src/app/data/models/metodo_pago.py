"""Entidad MetodoPago: el medio con el que un titular paga.

Los últimos cuatro dígitos no son un dato cosmético: son la llave de
emparejamiento con la que `ConciliacionService` decide a cuál tarjeta del
titular corresponde un cargo que llegó por correo. Solo se guardan esos
cuatro, nunca el número completo.

A diferencia de `Comercio` (que la ingesta resuelve o crea sola),
`MetodoPago` nunca se crea automáticamente: si los últimos cuatro dígitos no
casan con ninguno ya registrado, la compra se crea igual pero marcada
`requiere_revision` -inventar una tarjeta sería peor que dejarla sin
emparejar.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base
from app.data.models.enums import Moneda, TipoMetodoPago

if TYPE_CHECKING:
    from app.data.models.compra import Compra
    from app.data.models.usuario import Usuario


class MetodoPago(Base):
    """Un medio de pago propio de un titular: efectivo, una tarjeta, SINPE Móvil."""

    __tablename__ = "metodo_pago"
    __table_args__ = (
        UniqueConstraint("usuario_id", "alias", name="uq_metodo_pago_usuario_alias"),
        # NULL no choca contra NULL en una UNIQUE de SQL estándar: dos métodos
        # sin últimos cuatro (dos "Efectivo", por ejemplo) no violan esto. Es
        # el equivalente sin índice parcial de "últimos cuatro únicos por
        # titular, cuando los hay" -si el titular tuviera dos tarjetas
        # terminadas en 6411, el emparejamiento de la ingesta sería ambiguo.
        UniqueConstraint(
            "usuario_id", "ultimos_cuatro", name="uq_metodo_pago_usuario_ultimos_cuatro"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo: Mapped[TipoMetodoPago] = mapped_column(Enum(TipoMetodoPago), nullable=False)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda), nullable=False, default=Moneda.CRC)
    ultimos_cuatro: Mapped[str | None] = mapped_column(String(4), nullable=True)
    entidad: Mapped[str | None] = mapped_column(String(80), nullable=True)
    dia_corte: Mapped[int | None] = mapped_column(nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    usuario: Mapped["Usuario"] = relationship(back_populates="metodos_pago", lazy="select")
    # Sin cascada: dar de baja una tarjeta no puede borrar el historial de lo
    # que se pago con ella. Por eso `MetodoPago` tiene `activo` en vez de
    # borrarse, y por eso `Compra.metodo_pago_id` es nullable.
    compras: Mapped[list["Compra"]] = relationship(back_populates="metodo_pago", lazy="select")

    def __repr__(self) -> str:
        return f"MetodoPago(usuario_id={self.usuario_id!r}, alias={self.alias!r})"
