"""Repositorio generico con las operaciones que comparten todas las entidades."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.base import Base


class BaseRepository[ModeloT: Base]:
    """CRUD basico sobre una entidad.

    Los repositorios NO hacen commit: solo agregan y consultan. Quien decide
    cuando confirmar la transaccion es el servicio de negocio, porque es el unico
    que sabe si la operacion completa ya termino bien.
    """

    modelo: type[ModeloT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def obtener_por_id(self, entidad_id: int) -> ModeloT | None:
        return self.session.get(self.modelo, entidad_id)

    def listar(self, limite: int = 100, desplazamiento: int = 0) -> list[ModeloT]:
        sentencia = select(self.modelo).limit(limite).offset(desplazamiento)
        return list(self.session.scalars(sentencia))

    def agregar(self, entidad: ModeloT) -> ModeloT:
        self.session.add(entidad)
        self.session.flush()  # asigna el id sin cerrar la transaccion
        return entidad

    def eliminar(self, entidad: ModeloT) -> None:
        self.session.delete(entidad)
