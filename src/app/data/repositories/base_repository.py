"""CRUD generico compartido por todos los repositorios."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.base import Base


class BaseRepository[TEntidad: Base]:
    """Operaciones que toda entidad necesita, sin repetirlas una vez por tabla.

    Ningun metodo confirma la transaccion. El repositorio agrega y consulta; el
    `commit` lo hace el servicio, que es el unico que sabe si la operacion de
    negocio completa termino bien. Ese limite es el que mas adelante sostiene el
    proceso de conciliacion, que escribe en cinco tablas.
    """

    def __init__(self, sesion: Session, modelo: type[TEntidad]) -> None:
        self.sesion = sesion
        self.modelo = modelo

    def agregar(self, entidad: TEntidad) -> TEntidad:
        """Suma la entidad a la sesion y la vacia contra la base, sin confirmar.

        El `flush` es lo que hace que la entidad reciba su id, para que el
        servicio pueda seguir trabajando con ella dentro de la misma transaccion.
        """
        self.sesion.add(entidad)
        self.sesion.flush()
        return entidad

    def obtener_por_id(self, identificador: int) -> TEntidad | None:
        return self.sesion.get(self.modelo, identificador)

    def listar(self) -> list[TEntidad]:
        return list(self.sesion.scalars(select(self.modelo)))
