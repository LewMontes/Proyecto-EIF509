"""Entidad ComercioCategoriaSugerida: la categoría que un titular le asignó a un comercio."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base

if TYPE_CHECKING:
    from app.data.models.categoria import Categoria
    from app.data.models.comercio import Comercio
    from app.data.models.usuario import Usuario


class ComercioCategoriaSugerida(Base):
    """La categoría que un titular concreto le asignó a un comercio concreto.

    La propuesta de dominio original modela esto como un campo
    `categoria_sugerida` directo en `Comercio`. Como `Comercio` es un catálogo
    compartido entre titulares y `Categoria` es exclusiva de cada uno, una
    sugerencia global rompería el aislamiento entre cuentas: la categoría
    "Mascotas" del titular A no tiene por qué existir para el titular B, y
    mucho menos aplicarle su clasificación a sus compras. Esta tabla
    intermedia guarda la sugerencia por `(usuario, comercio)`, no por
    comercio solo -es la corrección al modelo, no una entidad nueva del
    dominio.

    Nace de "corregir crea la regla": cuando un titular cambia la categoría
    de un cargo, esta fila es lo que hace que la próxima compra en el mismo
    comercio entre ya clasificada.
    """

    __tablename__ = "comercio_categoria_sugerida"
    __table_args__ = (
        UniqueConstraint(
            "usuario_id", "comercio_id", name="uq_comercio_categoria_usuario_comercio"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    comercio_id: Mapped[int] = mapped_column(ForeignKey("comercio.id"), nullable=False, index=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"), nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="categorias_sugeridas", lazy="select")
    comercio: Mapped["Comercio"] = relationship(
        back_populates="categorias_sugeridas", lazy="select"
    )
    categoria: Mapped["Categoria"] = relationship(back_populates="sugerencias", lazy="select")

    def __repr__(self) -> str:
        return (
            f"ComercioCategoriaSugerida(usuario_id={self.usuario_id!r}, "
            f"comercio_id={self.comercio_id!r}, categoria_id={self.categoria_id!r})"
        )
