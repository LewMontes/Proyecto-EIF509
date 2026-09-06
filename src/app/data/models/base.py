"""Base declarativa comun a todas las entidades."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Raiz del mapeo declarativo de SQLAlchemy 2.0.

    Toda entidad hereda de aqui, y por eso Base.metadata conoce el esquema
    completo y puede crearlo de una sola vez.
    """
