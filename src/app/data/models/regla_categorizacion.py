"""Entidad ReglaCategorizacion: lo que el sistema aprende de las correcciones.

Nace de que el titular corrija una categoría, no de que entre a una pantalla
de configuración. Las reglas se evalúan por prioridad ascendente y gana la
primera que coincide, para que el usuario pueda poner excepciones específicas
antes que las generales.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base
from app.data.models.enums import CampoRegla

if TYPE_CHECKING:
    from app.data.models.categoria import Categoria
    from app.data.models.usuario import Usuario


class ReglaCategorizacion(Base):
    """Una regla de un titular que afina la clasificación automática."""

    __tablename__ = "regla_categorizacion"
    __table_args__ = (
        UniqueConstraint("usuario_id", "nombre", name="uq_regla_usuario_nombre"),
        # Con dos reglas del mismo titular en la misma prioridad, la
        # categorización dependería del orden en que la base devolviera las
        # filas: la misma compra podría caer en una categoría distinta en dos
        # corridas. La unicidad es lo que hace determinista el motor.
        UniqueConstraint("usuario_id", "prioridad", name="uq_regla_usuario_prioridad"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    categoria_destino_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    campo: Mapped[CampoRegla] = mapped_column(
        Enum(CampoRegla), nullable=False, default=CampoRegla.COMERCIO_NORMALIZADO
    )
    patron: Mapped[str] = mapped_column(String(200), nullable=False)
    prioridad: Mapped[int] = mapped_column(nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    veces_aplicada: Mapped[int] = mapped_column(nullable=False, default=0)

    usuario: Mapped["Usuario"] = relationship(back_populates="reglas_categorizacion", lazy="select")
    categoria_destino: Mapped["Categoria"] = relationship(
        back_populates="reglas_destino", lazy="select"
    )

    def __repr__(self) -> str:
        return f"ReglaCategorizacion(usuario_id={self.usuario_id!r}, nombre={self.nombre!r})"
