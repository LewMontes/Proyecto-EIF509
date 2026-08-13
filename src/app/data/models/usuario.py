"""Entidad Usuario."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import AuditoriaMixin, Base
from app.data.models.enums import Moneda

if TYPE_CHECKING:
    from app.data.models.categoria import Categoria


class Usuario(Base, AuditoriaMixin):
    """Persona duena de sus gastos.

    Es la raiz de aislamiento del sistema: toda consulta se filtra por usuario,
    de modo que cualquier persona pueda crear su cuenta sin ver la de nadie mas.

    La contrasena y la vinculacion del buzon de correo se agregan en proximos
    laboratorios, junto con la autenticacion.
    """

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(120), nullable=False)
    correo: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    moneda_preferida: Mapped[Moneda] = mapped_column(default=Moneda.CRC, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    categorias: Mapped[list[Categoria]] = relationship(back_populates="usuario")
