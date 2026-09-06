"""Acceso a la coleccion `bitacora_compras` de MongoDB.

El repositorio del subdominio documental. Hasta antes de este archivo, era el
unico acceso a datos del sistema que vivia en `business/`:
`BitacoraComprasService` hablaba PyMongo directamente. Eso rompia la regla que
sostiene el resto de las capas -la de datos es el unico lugar que sabe como se
leen y guardan los datos- solo porque la base era documental y no relacional.

**Por que no hereda de `BaseRepository`.** El generico esta parametrizado sobre
una entidad de SQLAlchemy (`BaseRepository[TEntidad: Base]`) y su contrato -
`agregar` con `flush` sin confirmar, `obtener_por_id`, `listar`- es el de una
sesion transaccional. Mongo aca no tiene ni sesion ni transaccion: cada
escritura es un `update_one` con `upsert` que se resuelve sola. Forzar la misma
firma habria obligado a implementar metodos que no significan nada de este lado
-un `agregar` que no puede participar del `commit` del servicio seria una
mentira. Comparten la *posicion* en la arquitectura, no la implementacion.

**La politica de fallo.** Ninguno de estos metodos propaga un `PyMongoError`:
devuelven `False` o `None`. Es la traduccion, en el contrato del repositorio,
de lo que decide ADR-002 -la bitacora **explica** lo que paso, no lo **decide**,
y ningun total del sistema depende de ella. Que Mongo este caido no puede
revertir una compra que PostgreSQL ya confirmo.
"""

import logging
from datetime import datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.errors import PyMongoError

_registro = logging.getLogger(__name__)


class BitacoraRepository:
    """Lee y escribe la bitacora de trazabilidad de una compra.

    `coleccion` puede ser `None` -por ejemplo si Mongo no esta configurado en
    este ambiente- y entonces el repositorio no escribe ni lee nada, en vez de
    exigir que todo el sistema sepa de Mongo para poder arrancar.
    """

    def __init__(self, coleccion: Collection | None) -> None:
        self._coleccion = coleccion

    @property
    def disponible(self) -> bool:
        """Si hay una coleccion contra la cual trabajar."""
        return self._coleccion is not None

    def agregar_evento(
        self,
        compra_id: int,
        usuario_id: int,
        estado_actual: str,
        evento: dict[str, Any],
        ahora: datetime,
    ) -> bool:
        """Empuja `evento` a la bitacora de `compra_id`, creandola si es el primero.

        Un solo `update_one` con `upsert` en vez de "buscar, y si no existe
        insertar": la bitacora se abre y se agranda en la misma operacion
        atomica, sin una ventana entre las dos en la que dos ingestas
        simultaneas de la misma compra crearian dos documentos.

        Devuelve `False` si no habia coleccion o si Mongo rechazo la escritura.
        """
        if self._coleccion is None:
            return False
        try:
            self._coleccion.update_one(
                {"compra_id": compra_id},
                {
                    "$setOnInsert": {
                        "compra_id": compra_id,
                        "usuario_id": usuario_id,
                        "abierta_en": ahora,
                    },
                    "$set": {"estado_actual": estado_actual, "actualizada_en": ahora},
                    "$push": {"eventos": evento},
                },
                upsert=True,
            )
        except PyMongoError:
            _registro.warning(
                "No se pudo escribir el evento %s de la compra %s en la bitacora de Mongo.",
                evento.get("tipo"),
                compra_id,
                exc_info=True,
            )
            return False
        return True

    def eventos_de(self, compra_id: int) -> list[dict[str, Any]] | None:
        """Los eventos de una compra, en el orden en que ocurrieron.

        `None` si no hay Mongo disponible, si Mongo no respondio, o si la
        compra todavia no tiene ningun evento.
        """
        documento = self._documento_de(compra_id)
        return documento.get("eventos") if documento else None

    def cantidad_de_eventos(self, compra_id: int) -> int:
        """Cuantos eventos lleva la bitacora de esta compra. 0 si no existe.

        Proyecta solo `eventos` (`{"eventos": 1}`) para no traerse el documento
        completo cuando lo unico que se necesita es su largo.
        """
        documento = self._documento_de(compra_id, proyeccion={"eventos": 1})
        if documento is None:
            return 0
        return len(documento.get("eventos", []))

    def _documento_de(
        self, compra_id: int, proyeccion: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if self._coleccion is None:
            return None
        try:
            if proyeccion is None:
                return self._coleccion.find_one({"compra_id": compra_id})
            return self._coleccion.find_one({"compra_id": compra_id}, proyeccion)
        except PyMongoError:
            _registro.warning(
                "No se pudo leer la bitacora de la compra %s.", compra_id, exc_info=True
            )
            return None
