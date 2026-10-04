"""Endpoints de los métodos de pago de un titular.

Sin esto, `ConciliacionService` nunca tiene con qué emparejar los últimos
cuatro dígitos que trae un comprobante -un `MetodoPago` nunca se crea solo,
ver la nota en el modelo.
"""

from fastapi import APIRouter, Response, status

from app.business.services.metodo_pago_service import CrearMetodoPagoComando
from app.presentation.dependencies import ServicioDeMetodosPago, UsuarioActual
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import CrearMetodoPagoRequest, IdDeRuta, MetodoPagoResponse

router = APIRouter(prefix=f"{API_V1}/metodos-pago", tags=["metodos-pago"])


@router.post(
    "",
    response_model=MetodoPagoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un método de pago",
)
def crear(
    peticion: CrearMetodoPagoRequest,
    servicio: ServicioDeMetodosPago,
    usuario: UsuarioActual,
    respuesta: Response,
) -> MetodoPagoResponse:
    metodo_pago = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id,
            alias=peticion.alias,
            tipo=peticion.tipo,
            moneda=peticion.moneda,
            ultimos_cuatro=peticion.ultimos_cuatro,
            entidad=peticion.entidad,
            dia_corte=peticion.dia_corte,
        )
    )
    respuesta.headers["Location"] = ubicacion("metodos-pago", metodo_pago.id)
    return MetodoPagoResponse.model_validate(metodo_pago)


@router.get("", response_model=list[MetodoPagoResponse], summary="Listar los métodos de pago")
def listar(servicio: ServicioDeMetodosPago, usuario: UsuarioActual) -> list[MetodoPagoResponse]:
    return [MetodoPagoResponse.model_validate(m) for m in servicio.listar(usuario.id)]


@router.get(
    "/{metodo_pago_id}", response_model=MetodoPagoResponse, summary="Consultar un método de pago"
)
def obtener(
    metodo_pago_id: IdDeRuta, servicio: ServicioDeMetodosPago, usuario: UsuarioActual
) -> MetodoPagoResponse:
    return MetodoPagoResponse.model_validate(servicio.obtener(usuario.id, metodo_pago_id))


@router.delete(
    "/{metodo_pago_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar un método de pago",
)
def desactivar(
    metodo_pago_id: IdDeRuta, servicio: ServicioDeMetodosPago, usuario: UsuarioActual
) -> None:
    """Borrado lógico: un gasto histórico tiene que poder seguir mostrando con qué
    tarjeta se pagó. Por eso `204` sin cuerpo y el recurso sigue consultable."""
    servicio.desactivar(usuario.id, metodo_pago_id)
