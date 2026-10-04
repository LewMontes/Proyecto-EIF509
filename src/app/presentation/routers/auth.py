"""Autenticación: el endpoint que emite el token.

No hay `logout`: la API es *stateless* y el token no se guarda en ninguna
tabla, así que no hay nada que revocar del lado del servidor. Cerrar sesión es
responsabilidad del cliente -descartar el token-, y de todos modos vence solo.
"""

from fastapi import APIRouter

from app.business.services.auth_service import IniciarSesionComando
from app.presentation.dependencies import ServicioDeAuth
from app.presentation.rutas import API_V1
from app.presentation.schemas import ErrorResponse, LoginRequest, TokenResponse

router = APIRouter(prefix=f"{API_V1}/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión y obtener el token de acceso",
    responses={401: {"model": ErrorResponse, "description": "Correo o contraseña incorrectos."}},
)
def login(peticion: LoginRequest, servicio: ServicioDeAuth) -> TokenResponse:
    """Canjea correo y contraseña por un JWT.

    Es público -todavía no hay identidad, es justo lo que resuelve-. Responde
    `200` y no `201`: no crea ningún recurso que después se pueda consultar, el
    token no vive en el servidor.
    """
    sesion = servicio.iniciar_sesion(
        IniciarSesionComando(correo=peticion.correo, contrasena=peticion.contrasena)
    )
    return TokenResponse(
        access_token=sesion.access_token,
        expires_in=sesion.expira_en_segundos,
        rol=sesion.usuario.rol,
    )
