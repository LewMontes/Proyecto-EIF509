"""Entidad Categoria."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import AuditoriaMixin, Base

if TYPE_CHECKING:
    from app.data.models.usuario import Usuario


class Categoria(Base, AuditoriaMixin):
    """Clasificacion jerarquica del gasto: Alimentacion -> Supermercado.

    La jerarquia se autorreferencia con categoria_padre_id. Solo las categorias
    hoja pueden recibir gasto; las categorias padre existen para totalizar.
    """

    __tablename__ = "categoria"
    __table_args__ = (UniqueConstraint("usuario_id", "nombre", name="uq_categoria_usuario_nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)

    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Color hexadecimal con el que el frontend pinta esta categoria en los graficos.
    color_hex: Mapped[str] = mapped_column(String(7), default="#6B7280", nullable=False)

    categoria_padre_id: Mapped[int | None] = mapped_column(
        ForeignKey("categoria.id"), nullable=True, index=True
    )
    es_hoja: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    usuario: Mapped[Usuario] = relationship(back_populates="categorias")
    categoria_padre: Mapped[Categoria | None] = relationship(
        back_populates="subcategorias", remote_side="Categoria.id"
    )
    subcategorias: Mapped[list[Categoria]] = relationship(back_populates="categoria_padre")
