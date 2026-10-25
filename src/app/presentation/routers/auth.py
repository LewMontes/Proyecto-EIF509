"""Autenticación: el endpoint que emite el token.

No hay `logout`: la API es *stateless* y el token no se guarda en ninguna
tabla, así que no hay nada que revocar del lado del servidor. Cerrar sesión es
responsabilidad del cliente -descartar el token-, y de todos modos vence solo.
"""

import logging

from fastapi import APIRouter

from app.business.services.auth_service import IniciarSesionComando
from app.presentation.dependencies import ServicioDeAuth
from app.presentation.errores import TIPO_DE_CONTENIDO, ProblemDetail
from app.presentation.rutas import API_V1
from app.presentation.schemas import LoginRequest, TokenResponse

registro_de_seguridad = logging.getLogger("gastonomo.seguridad")

router = APIRouter(prefix=f"{API_V1}/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión y obtener el token de acceso",
    responses={
        429: {
            "model": ProblemDetail,
            "description": "Demasiados intentos fallidos para esa cuenta. Ver `Retry-After`.",
            "content": {TIPO_DE_CONTENIDO: {}},
        }
    },
)
def login(peticion: LoginRequest, servicio: ServicioDeAuth) -> TokenResponse:
    """Canjea correo y contraseña por un JWT.

    Es público -todavía no hay identidad, es justo lo que resuelve-. Responde
    `200` y no `201`: no crea ningún recurso que después se pueda consultar, el
    token no vive en el servidor.

    Cinco intentos fallidos en 15 minutos bloquean esa cuenta 15 minutos
    (`429`). Los fallos los registra el manejador global como evento de
    seguridad; el éxito, este endpoint.
    """
    sesion = servicio.iniciar_sesion(
        IniciarSesionComando(correo=peticion.correo, contrasena=peticion.contrasena)
    )
    registro_de_seguridad.info(
        "Inicio de sesión exitoso",
        extra={"evento": "inicio_sesion_exitoso", "usuario_id": sesion.usuario.id},
    )
    return TokenResponse(
        access_token=sesion.access_token,
        expires_in=sesion.expira_en_segundos,
        rol=sesion.usuario.rol,
    )
