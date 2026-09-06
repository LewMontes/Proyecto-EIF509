"""Entidad Compra: el encabezado de un gasto de negocio real.

Los totales se persisten calculados en vez de derivarse de sus renglones en
cada consulta: un gasto histórico debe seguir mostrando lo que se pagó aunque
después cambie la tasa de cambio corregida. Nace de `ConciliacionService`
-para las que entran por correo- o de una captura manual futura.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base
from app.data.models.enums import EstadoCompra, Moneda, OrigenCompra
from app.data.models.tipos import FechaHoraUTC

if TYPE_CHECKING:
    from app.data.models.comercio import Comercio
    from app.data.models.comprobante import Comprobante
    from app.data.models.linea_compra import LineaCompra
    from app.data.models.metodo_pago import MetodoPago
    from app.data.models.usuario import Usuario


class Compra(Base):
    """Encabezado de una compra, con sus totales congelados."""

    __tablename__ = "compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    comercio_id: Mapped[int] = mapped_column(ForeignKey("comercio.id"), nullable=False, index=True)
    metodo_pago_id: Mapped[int | None] = mapped_column(ForeignKey("metodo_pago.id"), nullable=True)
    fecha: Mapped[date] = mapped_column(nullable=False, index=True)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    moneda: Mapped[Moneda] = mapped_column(Enum(Moneda), nullable=False, default=Moneda.CRC)
    estado: Mapped[EstadoCompra] = mapped_column(
        Enum(EstadoCompra), nullable=False, default=EstadoCompra.BORRADOR
    )
    origen: Mapped[OrigenCompra] = mapped_column(
        Enum(OrigenCompra), nullable=False, default=OrigenCompra.MANUAL
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    descuento: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    impuesto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    # Una compra que entró por correo nunca desglosa impuesto: el total ya
    # viene con IVA incluido y no se sabe qué parte era exenta.
    impuesto_desglosado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    tipo_cambio_aplicado: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=1)
    total_moneda_base: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    requiere_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creado_en: Mapped[datetime] = mapped_column(
        FechaHoraUTC, nullable=False, default=lambda: datetime.now(UTC)
    )

    # Estas cuatro relaciones son las que le faltaban al modelo, y por eso
    # `CompraService._detallar` resolvia a mano -una consulta por compra y por
    # campo- lo que le correspondia al ORM: 201 consultas para listar 50
    # compras. Ver docs/persistencia.md, seccion 5.
    #
    # Siguen siendo perezosas: la correccion no es cargarlas siempre, sino
    # pedirlas explicitamente en la consulta que si las va a usar
    # (`CompraRepository.listar_de_usuario`). Navegar a una compra suelta
    # -para validar que es del titular, por ejemplo- no tiene por que traer su
    # comercio ni sus renglones.
    usuario: Mapped["Usuario"] = relationship(back_populates="compras", lazy="select")
    comercio: Mapped["Comercio"] = relationship(back_populates="compras", lazy="select")
    metodo_pago: Mapped[Optional["MetodoPago"]] = relationship(
        back_populates="compras", lazy="select"
    )
    # `passive_deletes` porque el CASCADE ya lo hace la base
    # (`linea_compra.compra_id ON DELETE CASCADE`): sin esto SQLAlchemy
    # cargaria los renglones solo para borrarlos uno por uno, que es
    # exactamente el N+1 que este commit viene a quitar.
    lineas: Mapped[list["LineaCompra"]] = relationship(
        back_populates="compra",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )
    comprobantes: Mapped[list["Comprobante"]] = relationship(back_populates="compra", lazy="select")

    def __repr__(self) -> str:
        return f"Compra(id={self.id!r}, usuario_id={self.usuario_id!r}, total={self.total!r})"
