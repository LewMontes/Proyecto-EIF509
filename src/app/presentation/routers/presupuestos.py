"""Endpoints de los presupuestos por categoría y mes.

El consumo (`monto_consumido`) no se escribe por acá: lo acumulan los dos
procesos del dominio dentro de la transacción que registra cada compra, y lo
devuelve la anulación.
"""

from fastapi import APIRouter, Query, Response, status

from app.presentation.dependencies import ServicioDePresupuestos, UsuarioActual
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import (
    ActualizarPresupuestoRequest,
    CrearPresupuestoRequest,
    IdDeRuta,
    PresupuestoResponse,
)

router = APIRouter(prefix=f"{API_V1}/presupuestos", tags=["presupuestos"])


@router.post(
    "",
    response_model=PresupuestoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear el presupuesto de una categoría para un mes",
)
def crear(
    peticion: CrearPresupuestoRequest,
    servicio: ServicioDePresupuestos,
    usuario: UsuarioActual,
    respuesta: Response,
) -> PresupuestoResponse:
    """`409` si esa categoría ya tiene presupuesto en ese período: corregirlo es `PUT`."""
    presupuesto = servicio.crear(
        usuario_id=usuario.id,
        categoria_id=peticion.categoria_id,
        anio=peticion.anio,
        mes=peticion.mes,
        moneda=peticion.moneda,
        monto_limite=peticion.monto_limite,
        umbral_alerta=peticion.umbral_alerta,
    )
    respuesta.headers["Location"] = ubicacion("presupuestos", presupuesto.id)
    return PresupuestoResponse.model_validate(presupuesto)


@router.get(
    "", response_model=list[PresupuestoResponse], summary="Listar los presupuestos de un período"
)
def listar(
    servicio: ServicioDePresupuestos,
    usuario: UsuarioActual,
    anio: int = Query(ge=2000, le=2100),
    mes: int = Query(ge=1, le=12),
) -> list[PresupuestoResponse]:
    presupuestos = servicio.listar_del_periodo(usuario.id, anio, mes)
    return [PresupuestoResponse.model_validate(p) for p in presupuestos]


@router.get(
    "/{presupuesto_id}", response_model=PresupuestoResponse, summary="Consultar un presupuesto"
)
def obtener(
    presupuesto_id: IdDeRuta, servicio: ServicioDePresupuestos, usuario: UsuarioActual
) -> PresupuestoResponse:
    return PresupuestoResponse.model_validate(servicio.obtener(usuario.id, presupuesto_id))


@router.put(
    "/{presupuesto_id}",
    response_model=PresupuestoResponse,
    summary="Corregir el límite y el umbral de un presupuesto",
)
def actualizar(
    presupuesto_id: IdDeRuta,
    peticion: ActualizarPresupuestoRequest,
    servicio: ServicioDePresupuestos,
    usuario: UsuarioActual,
) -> PresupuestoResponse:
    presupuesto = servicio.actualizar(
        usuario.id, presupuesto_id, peticion.monto_limite, peticion.umbral_alerta
    )
    return PresupuestoResponse.model_validate(presupuesto)


@router.delete(
    "/{presupuesto_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar un presupuesto"
)
def eliminar(
    presupuesto_id: IdDeRuta, servicio: ServicioDePresupuestos, usuario: UsuarioActual
) -> None:
    servicio.eliminar(usuario.id, presupuesto_id)
