"""Endpoints de Comprobante: el Proceso 2 del dominio, expuesto.

`POST /comprobantes` **es** el Proceso 2 -ingesta y conciliación transaccional
de un comprobante-. Hasta el Laboratorio 4 ese proceso solo se podía ejecutar
desde las pruebas; acá queda conectado con la aplicación.

El recurso es el comprobante, no la conciliación: mandar uno lo crea, y la
respuesta dice en qué estado quedó y, si se concilió, a qué compra dio origen
(`compra_id`). Reintentar uno que quedó pendiente crea un intento nuevo, y por
eso es `POST /comprobantes/{id}/reintentos` -un sustantivo-.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.business.services.comprobante_service import RegistrarComprobanteComando
from app.data.models.enums import EstadoComprobante
from app.presentation.dependencies import ServicioDeComprobantes, UsuarioActual
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import ComprobanteResponse, IdDeRuta, RegistrarComprobanteRequest

router = APIRouter(prefix=f"{API_V1}/comprobantes", tags=["comprobantes"])


@router.post(
    "",
    response_model=ComprobanteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Recibir un comprobante y conciliarlo en una compra (Proceso 2)",
)
def registrar(
    peticion: RegistrarComprobanteRequest,
    servicio: ServicioDeComprobantes,
    usuario: UsuarioActual,
    respuesta: Response,
) -> ComprobanteResponse:
    """El Proceso 2 del dominio.

    Deja la constancia del mensaje y dispara la conciliación: emparejar el
    método de pago, resolver el comercio, categorizar, crear la compra,
    acumular el presupuesto y ligar el comprobante -todo o nada-.

    `201` siempre que el comprobante quede recibido, se haya conciliado o no:
    lo que se creó es el comprobante. `estado` dice qué pasó después
    -`PROCESADO` con su `compra_id`, `REVISION_MANUAL`, o `PARSEADO` si quedó
    pendiente del tipo de cambio-. `409` si ese mensaje ya se había recibido.
    """
    comprobante = servicio.registrar(
        RegistrarComprobanteComando(
            usuario_id=usuario.id,
            cuenta_correo_id=peticion.cuenta_correo_id,
            mensaje_id=peticion.mensaje_id,
            remitente=peticion.remitente,
            banco=peticion.banco,
            comercio=peticion.comercio,
            monto=peticion.monto,
            moneda=peticion.moneda.value,
            fecha=peticion.fecha,
            ultimos_cuatro=peticion.ultimos_cuatro,
            tipo_transaccion=peticion.tipo_transaccion,
            confianza=peticion.confianza,
        )
    )
    respuesta.headers["Location"] = ubicacion("comprobantes", comprobante.id)
    return ComprobanteResponse.model_validate(comprobante)


@router.get(
    "", response_model=list[ComprobanteResponse], summary="Listar los comprobantes del titular"
)
def listar(
    servicio: ServicioDeComprobantes,
    usuario: UsuarioActual,
    estado: Annotated[
        EstadoComprobante | None,
        Query(description="Solo los que están en ese estado de la ingesta."),
    ] = None,
) -> list[ComprobanteResponse]:
    return [ComprobanteResponse.model_validate(c) for c in servicio.listar(usuario.id, estado)]


@router.get(
    "/{comprobante_id}", response_model=ComprobanteResponse, summary="Consultar un comprobante"
)
def obtener(
    comprobante_id: IdDeRuta, servicio: ServicioDeComprobantes, usuario: UsuarioActual
) -> ComprobanteResponse:
    return ComprobanteResponse.model_validate(servicio.obtener(usuario.id, comprobante_id))


@router.post(
    "/{comprobante_id}/reintentos",
    response_model=ComprobanteResponse,
    summary="Reintentar la conciliación de un comprobante pendiente",
)
def reintentar(
    comprobante_id: IdDeRuta, servicio: ServicioDeComprobantes, usuario: UsuarioActual
) -> ComprobanteResponse:
    """Para el comprobante que quedó esperando el tipo de cambio de su fecha, o que
    falló una o dos veces.

    `409` si su estado no admite otro intento: `PROCESADO` ya tiene su compra,
    `FALLIDO` agotó los tres, `REVISION_MANUAL` lo resuelve una persona.
    """
    return ComprobanteResponse.model_validate(servicio.reintentar(usuario.id, comprobante_id))
