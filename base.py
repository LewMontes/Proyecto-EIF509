"""Base declarativa de SQLAlchemy y piezas comunes a todas las entidades."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Clase madre de todas las entidades. Alembic la usa para detectar cambios."""


class AuditoriaMixin:
    """Marcas de tiempo de creacion y ultima modificacion.

    Se aplica a toda entidad persistida: sin esto no hay trazabilidad de cuando
    se registro o se corrigio un gasto, y la trazabilidad es el corazon de este sistema.
    """

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
