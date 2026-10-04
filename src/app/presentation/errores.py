"""El manejador global de errores: todo lo que sale mal, sale como Problem Details.

Es el equivalente de un `@RestControllerAdvice`: un único lugar que atrapa las
excepciones de toda la API y las traduce a una respuesta HTTP. Ningún router
tiene un `try/except` ni arma un error a mano.

El formato es **RFC 9457 (Problem Details for HTTP APIs)**: `Content-Type:
application/problem+json` y un cuerpo con cinco miembros estándar.

    {
      "type":     "https://.../docs/api.md#regla-de-negocio-violada",
      "title":    "La operación choca con el estado actual del recurso",
      "status":   409,
      "detail":   "'Alimentación' es una categoría padre; solo las hojas reciben gasto.",
      "instance": "/api/v1/compras",
      "codigo":   "CategoriaNoEsHoja"
    }

- `type` identifica la **clase** de problema y apunta a su documentación.
- `title` es el resumen fijo de esa clase; no cambia de una ocurrencia a otra.
- `detail` es lo específico de **esta** ocurrencia: el mensaje de la regla.
- `instance` es la ruta que se pidió.
- `codigo` es una extensión -el RFC las permite-: el nombre de la regla de
  negocio que falló, para que un cliente decida sin interpretar un texto.

**Ninguna traza llega al cliente.** Lo que no es un error de negocio conocido
cae en el manejador de `Exception`, que responde un 500 genérico y deja la
traza donde corresponde: en el log del servidor.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.business.errors import (
    AccesoDenegado,
    DatosInvalidos,
    ErrorDeNegocio,
    ErrorDeProveedorExterno,
    NoAutenticado,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
)

registro = logging.getLogger("gastonomo.api")

TIPO_DE_CONTENIDO = "application/problem+json"
# Cada `type` es una URL que resuelve a la sección de la documentación que
# explica esa clase de problema.
_BASE_DE_TIPOS = "https://github.com/LewMontes/Proyecto-EIF509/blob/master/docs/api.md#"


class CampoInvalido(BaseModel):
    """Un campo de la petición que no pasó la validación de formato."""

    campo: str = Field(examples=["body.lineas.0.cantidad"])
    mensaje: str = Field(examples=["Input should be greater than 0"])


class ProblemDetail(BaseModel):
    """El cuerpo de todo error de la API (RFC 9457)."""

    type: str = Field(description="URI que identifica la clase de problema.")
    title: str = Field(description="Resumen fijo de la clase de problema.")
    status: int = Field(description="El código HTTP, repetido en el cuerpo.")
    detail: str = Field(description="Qué pasó en esta ocurrencia concreta.")
    instance: str = Field(description="La ruta que se pidió.")
    codigo: str | None = Field(
        default=None, description="Nombre de la regla de negocio que falló, si fue una."
    )
    errores: list[CampoInvalido] | None = Field(
        default=None, description="Solo en un 400: cada campo que no pasó la validación."
    )


# Familia de error → (código HTTP, ancla en la documentación, título).
# Se recorre en orden y gana la primera que calza, así que una familia más
# específica tiene que ir antes que la que la contiene.
_FAMILIAS: tuple[tuple[type[ErrorDeNegocio], int, str, str], ...] = (
    (
        NoAutenticado,
        401,
        "no-autenticado",
        "Hace falta un token de acceso válido",
    ),
    (
        AccesoDenegado,
        403,
        "acceso-denegado",
        "La cuenta no tiene permiso para esta operación",
    ),
    (
        RecursoNoEncontrado,
        404,
        "recurso-no-encontrado",
        "El recurso no existe en esta cuenta",
    ),
    (
        ReglaDeNegocioViolada,
        409,
        "regla-de-negocio-violada",
        "La operación choca con el estado actual del recurso",
    ),
    (
        DatosInvalidos,
        422,
        "datos-invalidos",
        "Los datos no cumplen una regla del dominio",
    ),
    (
        ErrorDeProveedorExterno,
        502,
        "proveedor-externo",
        "Un servicio externo no respondió",
    ),
)

# Lo que cada endpoint puede responder, para que quede en el contrato OpenAPI.
# Declarar el 422 acá además reemplaza al `HTTPValidationError` que FastAPI
# documenta por defecto, que ya no es lo que esta API devuelve.
RESPUESTAS_DE_ERROR: dict[int | str, dict[str, Any]] = {
    codigo: {
        "model": ProblemDetail,
        "description": descripcion,
        "content": {TIPO_DE_CONTENIDO: {}},
    }
    for codigo, descripcion in (
        (400, "La petición está mal formada: un campo no pasó la validación de formato."),
        (401, "Falta el token, venció o no es válido."),
        (403, "El rol de la cuenta no alcanza, o el recurso es de otra cuenta."),
        (404, "El recurso no existe, o no pertenece al titular."),
        (409, "La operación choca con el estado actual del recurso."),
        (422, "Los datos están bien formados pero no cumplen una regla del dominio."),
    )
}


def documentar_errores_como_problem_details(app: FastAPI) -> None:
    """Hace que el contrato OpenAPI describa los errores con su tipo de contenido real.

    Al declarar una respuesta con `model`, FastAPI publica su esquema bajo
    `application/json`. Los errores de esta API salen como
    `application/problem+json`, así que acá se mueve el esquema al tipo de
    contenido que de verdad viaja: lo que dice Swagger UI coincide con lo que
    el cliente recibe.
    """
    generar = app.openapi

    def _contrato() -> dict[str, Any]:
        if app.openapi_schema is None:
            esquema = generar()
            for operaciones in esquema["paths"].values():
                for operacion in operaciones.values():
                    for respuesta in operacion.get("responses", {}).values():
                        contenido = respuesta.get("content", {})
                        if TIPO_DE_CONTENIDO in contenido and "application/json" in contenido:
                            contenido[TIPO_DE_CONTENIDO] = contenido.pop("application/json")
        return app.openapi_schema

    app.openapi = _contrato


def _problema(
    peticion: Request,
    status: int,
    ancla: str | None,
    titulo: str,
    detalle: str,
    codigo: str | None = None,
    errores: list[CampoInvalido] | None = None,
    encabezados: dict[str, str] | None = None,
) -> JSONResponse:
    cuerpo = ProblemDetail(
        # `about:blank` es lo que el RFC indica cuando el problema no tiene más
        # semántica que la de su código HTTP.
        type=f"{_BASE_DE_TIPOS}{ancla}" if ancla else "about:blank",
        title=titulo,
        status=status,
        detail=detalle,
        instance=peticion.url.path,
        codigo=codigo,
        errores=errores,
    )
    return JSONResponse(
        status_code=status,
        content=cuerpo.model_dump(exclude_none=True),
        media_type=TIPO_DE_CONTENIDO,
        headers=encabezados,
    )


def registrar_manejadores_de_error(app: FastAPI) -> None:
    """Registra los manejadores globales. Es el único lugar que conoce los códigos HTTP."""

    @app.exception_handler(ErrorDeNegocio)
    def _de_negocio(peticion: Request, error: ErrorDeNegocio) -> JSONResponse:
        """Toda excepción del dominio, traducida según la familia de la que hereda.

        Un solo manejador para toda la jerarquía: una regla con nombre nueva
        -`CategoriaNoEsHoja`, `CuadreFueraDeTolerancia`- no necesita registrarse
        acá, hereda el código de su familia y aporta su nombre como `codigo`.
        """
        for familia, status, ancla, titulo in _FAMILIAS:
            if isinstance(error, familia):
                # El 401 lleva el encabezado que le dice al cliente cómo autenticarse.
                encabezados = {"WWW-Authenticate": "Bearer"} if status == 401 else None
                return _problema(
                    peticion,
                    status,
                    ancla,
                    titulo,
                    str(error),
                    codigo=type(error).__name__,
                    encabezados=encabezados,
                )
        # Un `ErrorDeNegocio` que no pertenece a ninguna familia es un descuido
        # de programación, no un error del cliente.
        return _error_interno(peticion, error)

    @app.exception_handler(RequestValidationError)
    def _de_formato(peticion: Request, error: RequestValidationError) -> JSONResponse:
        """La validación de los DTOs (el equivalente de `@Valid`): 400, no 422.

        FastAPI responde 422 por defecto. Acá se separan las dos cosas que ese
        código mezclaba: **400** es una petición mal formada -un tipo
        equivocado, un campo obligatorio que falta, un monto negativo- y
        **422** queda para lo que está bien formado pero rompe una regla del
        dominio. El cliente distingue «arreglá el formulario» de «esto no se
        puede hacer» sin leer el mensaje.
        """
        errores = [
            CampoInvalido(
                campo=".".join(str(parte) for parte in fallo["loc"]), mensaje=fallo["msg"]
            )
            for fallo in error.errors()
        ]
        return _problema(
            peticion,
            400,
            "solicitud-mal-formada",
            "La petición está mal formada",
            f"{len(errores)} campo(s) no pasaron la validación de formato.",
            errores=errores,
        )

    @app.exception_handler(StarletteHTTPException)
    def _de_http(peticion: Request, error: StarletteHTTPException) -> JSONResponse:
        """Los errores que produce el propio framework: ruta inexistente, método no permitido."""
        return _problema(
            peticion,
            error.status_code,
            None,
            HTTPStatus(error.status_code).phrase,
            str(error.detail),
            encabezados=dict(error.headers) if error.headers else None,
        )

    @app.exception_handler(IntegrityError)
    def _de_integridad(peticion: Request, error: IntegrityError) -> JSONResponse:
        """Una restricción de la base que ninguna regla del servicio atrapó antes.

        Pasa cuando dos peticiones simultáneas pasan la misma validación y la
        segunda choca contra el `UNIQUE`. Se responde 409 sin repetir el
        mensaje del motor, que nombra tablas y restricciones.
        """
        registro.warning("Violación de integridad en %s", peticion.url.path, exc_info=error)
        return _problema(
            peticion,
            409,
            "regla-de-negocio-violada",
            "La operación choca con el estado actual del recurso",
            "La operación entra en conflicto con datos que ya existen.",
        )

    @app.exception_handler(Exception)
    def _inesperado(peticion: Request, error: Exception) -> JSONResponse:
        return _error_interno(peticion, error)


def _error_interno(peticion: Request, error: Exception) -> JSONResponse:
    """500 genérico. La traza va al log; al cliente, nada que describa el interior."""
    registro.error("Error no controlado en %s", peticion.url.path, exc_info=error)
    return _problema(
        peticion,
        500,
        "error-interno",
        "Error interno del servidor",
        "Ocurrió un error inesperado. El equipo ya tiene el registro de lo que pasó.",
    )
