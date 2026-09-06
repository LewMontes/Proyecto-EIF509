"""Armado de las dependencias de cada peticion.

Es el unico lugar de la capa de presentacion que conoce a los repositorios, y
solo para inyectarlos: los routers reciben el servicio ya construido y nunca
tocan la base directamente.

Cada dependencia arma su servicio con los repositorios que necesita, sobre la
sesion de ESTA peticion. La sesion vive lo que dura la peticion y se cierra
siempre -`obtener_sesion` lo garantiza con su `finally`- asi que dos peticiones
simultaneas nunca comparten estado de SQLAlchemy.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.categoria_service import CategoriaService
from app.business.services.compra_service import CompraService
from app.config.cliente_mongo import obtener_coleccion_bitacora
from app.config.database import obtener_sesion
from app.data.repositories.bitacora_repository import BitacoraRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.compra_repository import CompraRepository

SesionDependencia = Annotated[Session, Depends(obtener_sesion)]


def obtener_servicio_de_categorias(sesion: SesionDependencia) -> CategoriaService:
    """Arma el servicio de categorias sobre la sesion actual."""
    return CategoriaService(CategoriaRepository(sesion))


ServicioCategoria = Annotated[CategoriaService, Depends(obtener_servicio_de_categorias)]


def obtener_servicio_de_compras(sesion: SesionDependencia) -> CompraService:
    """Arma el servicio de lectura de compras sobre la sesion actual.

    Le basta el repositorio de `Compra`: los nombres que la lista y el detalle
    muestran -comercio, metodo de pago, categoria- llegan por las relaciones
    que ese repositorio carga en la misma consulta, no por un repositorio
    aparte para cada uno. Ver docs/persistencia.md, seccion 5.
    """
    return CompraService(CompraRepository(sesion))


ServicioDeCompras = Annotated[CompraService, Depends(obtener_servicio_de_compras)]


def obtener_servicio_de_bitacora() -> BitacoraComprasService:
    """Arma el servicio de bitacora sobre la coleccion de Mongo compartida.

    No recibe la sesion de SQLAlchemy: la bitacora vive en Mongo, no en
    PostgreSQL, y no participa de la transaccion de negocio (ver ADR-002).

    `obtener_coleccion_bitacora()` nunca falla por si sola -la conexion de
    PyMongo es perezosa- asi que este servicio siempre se puede construir,
    incluso si Mongo termina no respondiendo cuando de verdad se intenta
    escribir. Ese caso lo absorbe `BitacoraRepository`, que devuelve `False`
    en vez de propagar el error.
    """
    return BitacoraComprasService(BitacoraRepository(obtener_coleccion_bitacora()))


ServicioDeBitacora = Annotated[BitacoraComprasService, Depends(obtener_servicio_de_bitacora)]
