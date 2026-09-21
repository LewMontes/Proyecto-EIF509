"""Endpoints del límite de los presupuestos (CRUD).

El consumo real -que combina esto con el gasto ya clasificado- vive en
`GET /api/cuentas-correo/{cuenta_id}/presupuestos`, porque necesita leer
correo y no tiene sentido en un router que solo conoce presupuestos.
"""

from fastapi import APIRouter, Query

from app.presentation.dependencies import (
    ServicioDePresupuestos,
)
from app.presentation.schemas import CrearPresupuestoRequest, PresupuestoResponse

router = APIRouter(prefix="/api/presupuestos", tags=["presupuestos"])


@router.post("", response_model=PresupuestoResponse, summary="Crear o corregir un presupuesto")
def crear_o_actualizar(
    peticion: CrearPresupuestoRequest,
    servicio: ServicioDePresupuestos,
) -> PresupuestoResponse:
    presupuesto = servicio.crear_o_actualizar(
        usuario_id=peticion.usuario_id,
        categoria_id=peticion.categoria_id,
        anio=peticion.anio,
        mes=peticion.mes,
        moneda=peticion.moneda,
        monto_limite=peticion.monto_limite,
        umbral_alerta=peticion.umbral_alerta,
    )
    return PresupuestoResponse.model_validate(presupuesto)


@router.get(
    "", response_model=list[PresupuestoResponse], summary="Listar los presupuestos de un período"
)
def listar(
    servicio: ServicioDePresupuestos,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
    anio: int = Query(ge=2000, le=2100),
    mes: int = Query(ge=1, le=12),
) -> list[PresupuestoResponse]:
    presupuestos = servicio.listar_del_periodo(usuario_id, anio, mes)
    return [PresupuestoResponse.model_validate(p) for p in presupuestos]


@router.delete("/{presupuesto_id}", status_code=204, summary="Eliminar un presupuesto")
def eliminar(
    presupuesto_id: int,
    servicio: ServicioDePresupuestos,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> None:
    servicio.eliminar(usuario_id, presupuesto_id)
