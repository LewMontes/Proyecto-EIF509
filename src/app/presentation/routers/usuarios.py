"""Endpoints de las cuentas.

Es el router donde conviven los tres niveles de acceso de la API:

- **Público** · `POST /usuarios` -registrarse no puede exigir estar registrado.
- **Autenticado** · `GET /usuarios/yo` y `GET /usuarios/{id}` -cualquier rol,
  pero `{id}` solo responde si la cuenta es la propia (lo verifica el servicio).
- **Solo `ADMIN`** · `GET /usuarios` -la lista de todas las cuentas.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.business.services.usuario_service import RegistrarUsuarioComando, UsuarioService
from app.data.paginacion import SolicitudDePagina
from app.presentation.dependencies import Administrador, ServicioDeUsuarios, UsuarioActual
from app.presentation.paginacion import (
    PaginaResponse,
    parametros_de_pagina,
    respuesta_de_pagina,
)
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import IdDeRuta, RegistrarUsuarioRequest, UsuarioResponse

router = APIRouter(prefix=f"{API_V1}/usuarios", tags=["usuarios"])

PaginaDeUsuarios = Annotated[
    SolicitudDePagina,
    Depends(parametros_de_pagina(UsuarioService.CAMPOS_ORDENABLES, "correo,asc")),
]


@router.post(
    "",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una cuenta nueva",
)
def registrar(
    peticion: RegistrarUsuarioRequest, servicio: ServicioDeUsuarios, respuesta: Response
) -> UsuarioResponse:
    """Crea la cuenta, siempre con rol `TITULAR`. Público."""
    usuario = servicio.registrar(
        RegistrarUsuarioComando(
            nombre_completo=peticion.nombre_completo,
            correo=peticion.correo,
            contrasena=peticion.contrasena,
        )
    )
    respuesta.headers["Location"] = ubicacion("usuarios", usuario.id)
    return UsuarioResponse.model_validate(usuario)


@router.get("", response_model=PaginaResponse[UsuarioResponse], summary="Listar todas las cuentas")
def listar(
    servicio: ServicioDeUsuarios, _: Administrador, pagina: PaginaDeUsuarios
) -> PaginaResponse[UsuarioResponse]:
    """Solo `ADMIN`: un titular que lo pide recibe `403`. Paginada."""
    return respuesta_de_pagina(servicio.listar(pagina), UsuarioResponse.model_validate)


@router.get("/yo", response_model=UsuarioResponse, summary="La cuenta del token actual")
def yo(servicio: ServicioDeUsuarios, usuario: UsuarioActual) -> UsuarioResponse:
    """Va **antes** de `/{usuario_id}`: FastAPI resuelve las rutas en orden de
    declaración, y si estuviera después `yo` entraría por la ruta del id."""
    return UsuarioResponse.model_validate(servicio.obtener(usuario, usuario.id))


@router.get("/{usuario_id}", response_model=UsuarioResponse, summary="Consultar una cuenta")
def obtener(
    usuario_id: IdDeRuta, servicio: ServicioDeUsuarios, usuario: UsuarioActual
) -> UsuarioResponse:
    """La propia, o cualquiera si quien pide es `ADMIN`. La de otro titular da `403`.

    El router no decide nada: le pasa al servicio quién pide y qué pide, y es
    el servicio el que verifica la propiedad del recurso.
    """
    return UsuarioResponse.model_validate(servicio.obtener(usuario, usuario_id))
