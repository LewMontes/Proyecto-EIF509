"""Tipos de columna compartidos entre entidades."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class FechaHoraUTC(TypeDecorator):
    """Guarda datetimes conscientes de zona horaria en una columna DateTime plana.

    SQLite no tiene un tipo de fecha nativo: SQLAlchemy lo emula guardando
    texto. El texto que arma para un datetime "aware" incluye el desfase
    (`+00:00`), pero el analizador con el que después lo relee no lo entiende
    y devuelve un datetime "naive". Mientras el objeto siga vivo en el mapa de
    identidad de la sesión no se nota, porque no hay ida y vuelta a la base;
    pero apenas se recolecta -tan pronto como nada más lo referencia, algo tan
    común como terminar de atender la petición anterior- la siguiente consulta
    trae la versión sin zona horaria, y compararla contra `datetime.now(UTC)`
    revienta con `TypeError: can't compare offset-naive and offset-aware
    datetimes`.

    Este tipo cierra ese hueco en el borde: al guardar, quita el desfase y
    deja el valor en UTC; al leer, se lo vuelve a poner. El resto del sistema
    nunca ve, viniendo de la base, un datetime sin zona horaria.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "FechaHoraUTC solo acepta datetimes con zona horaria "
                "(usar datetime.now(UTC), no datetime.now())."
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)
