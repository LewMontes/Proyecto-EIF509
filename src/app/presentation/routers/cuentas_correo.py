"""Endpoints de los buzones del titular.

Todo comprobante pertenece a un buzón, así que este es el recurso que hay que
crear antes de mandar el primero a `POST /api/v1/comprobantes`.
"""

from fastapi import APIRouter, Response, status

from app.presentation.dependencies import ServicioDeCuentasCorreo, UsuarioActual
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import CuentaCorreoResponse, IdDeRuta, RegistrarCuentaCorreoRequest

router = APIRouter(prefix=f"{API_V1}/cuentas-correo", tags=["cuentas-correo"])


@router.post(
    "",
    response_model=CuentaCorreoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un buzón del titular",
)
def registrar(
    peticion: RegistrarCuentaCorreoRequest,
    servicio: ServicioDeCuentasCorreo,
    usuario: UsuarioActual,
    respuesta: Response,
) -> CuentaCorreoResponse:
    cuenta = servicio.registrar(usuario.id, peticion.proveedor, peticion.direccion)
    respuesta.headers["Location"] = ubicacion("cuentas-correo", cuenta.id)
    return CuentaCorreoResponse.model_validate(cuenta)


@router.get("", response_model=list[CuentaCorreoResponse], summary="Listar los buzones del titular")
def listar(servicio: ServicioDeCuentasCorreo, usuario: UsuarioActual) -> list[CuentaCorreoResponse]:
    return [CuentaCorreoResponse.model_validate(c) for c in servicio.listar(usuario.id)]


@router.get(
    "/{cuenta_correo_id}", response_model=CuentaCorreoResponse, summary="Consultar un buzón"
)
def obtener(
    cuenta_correo_id: IdDeRuta, servicio: ServicioDeCuentasCorreo, usuario: UsuarioActual
) -> CuentaCorreoResponse:
    return CuentaCorreoResponse.model_validate(servicio.obtener(usuario.id, cuenta_correo_id))
