"""Endpoints de los métodos de pago de un titular.

Sin esto, `ConciliacionService` nunca tiene con qué emparejar los últimos
cuatro dígitos que trae un comprobante -un `MetodoPago` nunca se crea solo,
ver la nota en el modelo.
"""

from fastapi import APIRouter, Query

from app.business.services.metodo_pago_service import CrearMetodoPagoComando
from app.presentation.dependencies import (
    ServicioDeMetodosPago,
)
from app.presentation.schemas import CrearMetodoPagoRequest, MetodoPagoResponse

router = APIRouter(prefix="/api/metodos-pago", tags=["metodos-pago"])


@router.post("", response_model=MetodoPagoResponse, summary="Registrar un método de pago")
def crear(
    peticion: CrearMetodoPagoRequest,
    servicio: ServicioDeMetodosPago,
) -> MetodoPagoResponse:
    metodo_pago = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=peticion.usuario_id,
            alias=peticion.alias,
            tipo=peticion.tipo,
            moneda=peticion.moneda,
            ultimos_cuatro=peticion.ultimos_cuatro,
            entidad=peticion.entidad,
            dia_corte=peticion.dia_corte,
        )
    )
    return MetodoPagoResponse.model_validate(metodo_pago)


@router.get("", response_model=list[MetodoPagoResponse], summary="Listar los métodos de pago")
def listar(
    servicio: ServicioDeMetodosPago,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> list[MetodoPagoResponse]:
    return [MetodoPagoResponse.model_validate(m) for m in servicio.listar(usuario_id)]


@router.delete(
    "/{metodo_pago_id}", response_model=MetodoPagoResponse, summary="Desactivar un método de pago"
)
def desactivar(
    metodo_pago_id: int,
    servicio: ServicioDeMetodosPago,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> MetodoPagoResponse:
    return MetodoPagoResponse.model_validate(servicio.desactivar(usuario_id, metodo_pago_id))
