"""Endpoints de las reglas de categorización de un titular.

Son el primer eslabón automático de la cadena de categorización: lo que el
titular define acá es lo que `ReglasDelTitular` recorre por prioridad en los
dos procesos del dominio.
"""

from fastapi import APIRouter, Response, status

from app.business.services.regla_categorizacion_service import (
    CrearReglaComando,
    ReglaCategorizacionService,
)
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.presentation.dependencies import ServicioDeReglasCategorizacion, UsuarioActual
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import (
    CrearReglaCategorizacionRequest,
    IdDeRuta,
    ReglaCategorizacionResponse,
)

router = APIRouter(prefix=f"{API_V1}/reglas-categorizacion", tags=["reglas-categorizacion"])


def _respuesta(
    regla: ReglaCategorizacion, servicio: ReglaCategorizacionService
) -> ReglaCategorizacionResponse:
    return ReglaCategorizacionResponse(
        id=regla.id,
        usuario_id=regla.usuario_id,
        nombre=regla.nombre,
        campo=regla.campo,
        patron=regla.patron,
        categoria_destino_id=regla.categoria_destino_id,
        categoria_destino_nombre=servicio.nombre_de_categoria(regla.categoria_destino_id) or "",
        prioridad=regla.prioridad,
        activa=regla.activa,
        veces_aplicada=regla.veces_aplicada,
    )


@router.post(
    "",
    response_model=ReglaCategorizacionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una regla de categorización",
)
def crear(
    peticion: CrearReglaCategorizacionRequest,
    servicio: ServicioDeReglasCategorizacion,
    usuario: UsuarioActual,
    respuesta: Response,
) -> ReglaCategorizacionResponse:
    regla = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre=peticion.nombre,
            patron=peticion.patron,
            categoria_destino_id=peticion.categoria_destino_id,
            campo=peticion.campo,
            prioridad=peticion.prioridad,
        )
    )
    respuesta.headers["Location"] = ubicacion("reglas-categorizacion", regla.id)
    return _respuesta(regla, servicio)


@router.get(
    "",
    response_model=list[ReglaCategorizacionResponse],
    summary="Listar las reglas de categorización, por prioridad",
)
def listar(
    servicio: ServicioDeReglasCategorizacion, usuario: UsuarioActual
) -> list[ReglaCategorizacionResponse]:
    return [_respuesta(regla, servicio) for regla in servicio.listar(usuario.id)]


@router.get(
    "/{regla_id}",
    response_model=ReglaCategorizacionResponse,
    summary="Consultar una regla de categorización",
)
def obtener(
    regla_id: IdDeRuta, servicio: ServicioDeReglasCategorizacion, usuario: UsuarioActual
) -> ReglaCategorizacionResponse:
    return _respuesta(servicio.obtener(usuario.id, regla_id), servicio)


@router.delete(
    "/{regla_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar una regla de categorización",
)
def desactivar(
    regla_id: IdDeRuta, servicio: ServicioDeReglasCategorizacion, usuario: UsuarioActual
) -> None:
    """Borrado lógico: la regla conserva `veces_aplicada` como historial y sigue
    consultable por su id, ya con `activa: false`."""
    servicio.desactivar(usuario.id, regla_id)
