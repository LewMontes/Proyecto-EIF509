"""Entidades de negocio mapeadas con SQLAlchemy.

Importarlas todas aqui es lo que hace que Base.metadata las conozca, que es de
donde salen la creacion de tablas y, mas adelante, las migraciones.

El Laboratorio 1 entrega dos entidades: las necesarias para demostrar el
recorrido completo por las capas. Las otras nueve del dominio estan disenadas en
docs/propuesta-dominio.md y se implementan en proximos laboratorios.
"""

from app.data.models.base import AuditoriaMixin, Base
from app.data.models.categoria import Categoria
from app.data.models.enums import Moneda
from app.data.models.usuario import Usuario

__all__ = [
    "AuditoriaMixin",
    "Base",
    "Categoria",
    "Moneda",
    "Usuario",
]
