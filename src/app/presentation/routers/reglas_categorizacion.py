"""Endpoints de las reglas de categorización de un titular.

Sin esto, `ReglaCategorizacion` era un modelo y un motor de evaluación sin
ningún dueño real -ver la nota en `regla_categorizacion_service.py`.
"""

from fastapi import APIRouter, Query

from app.business.services.regla_categorizacion_service import (
    CrearReglaComando,
    ReglaCategorizacionService,
)
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.presentation.dependencies import (
    ServicioDeReglasCategorizacion,
)
from app.presentation.schemas import CrearReglaCategorizacionRequest, ReglaCategorizacionResponse

router = APIRouter(prefix="/api/reglas-categorizacion", tags=["reglas-categorizacion"])


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
    "", response_model=ReglaCategorizacionResponse, summary="Crear una regla de categorización"
)
def crear(
    peticion: CrearReglaCategorizacionRequest,
    servicio: ServicioDeReglasCategorizacion,
) -> ReglaCategorizacionResponse:
    regla = servicio.crear(
        CrearReglaComando(
            usuario_id=peticion.usuario_id,
            nombre=peticion.nombre,
            patron=peticion.patron,
            categoria_destino_id=peticion.categoria_destino_id,
            campo=peticion.campo,
            prioridad=peticion.prioridad,
        )
    )
    return _respuesta(regla, servicio)


@router.get(
    "",
    response_model=list[ReglaCategorizacionResponse],
    summary="Listar las reglas de categorización",
)
def listar(
    servicio: ServicioDeReglasCategorizacion,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> list[ReglaCategorizacionResponse]:
    return [_respuesta(regla, servicio) for regla in servicio.listar(usuario_id)]


@router.delete(
    "/{regla_id}",
    response_model=ReglaCategorizacionResponse,
    summary="Desactivar una regla de categorización",
)
def desactivar(
    regla_id: int,
    servicio: ServicioDeReglasCategorizacion,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> ReglaCategorizacionResponse:
    regla = servicio.desactivar(usuario_id, regla_id)
    return _respuesta(regla, servicio)
