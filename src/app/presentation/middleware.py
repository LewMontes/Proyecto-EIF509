"""Lo que pasa alrededor de cada petición, antes y después del router.

Dos piezas, las dos del Laboratorio 7:

- `RegistroDePeticiones` le pone un id a cada petición y escribe una línea de
  acceso estructurada cuando termina. Con ese id se juntan todas las líneas
  que una misma petición produjo -la de acceso, la del evento de seguridad, la
  traza de un 500- y el cliente lo recibe en `X-Request-ID` para poder citarlo.
- `CabecerasDeSeguridad` agrega a toda respuesta las cabeceras que le dicen al
  navegador qué no hacer con ella (OWASP A02:2025, configuración insegura).
"""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config.registros import id_peticion_actual

registro_de_acceso = logging.getLogger("gastonomo.acceso")

ENCABEZADO_ID_PETICION = "X-Request-ID"
# Un id que manda el cliente se acepta solo si es corto y sin caracteres raros:
# va a parar al registro, y un salto de línea ahí permitiría inventar líneas.
_ID_ACEPTABLE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Rutas que se consultan cada pocos segundos (la plataforma, el HEALTHCHECK del
# contenedor). Su línea de acceso baja a DEBUG para no tapar las que importan.
_RUTAS_DE_SONDEO = ("/actuator/health", "/api/salud")


def ip_de(peticion: Request) -> str | None:
    """La IP de quien pide. Detrás del proxy de la plataforma, uvicorn la toma de
    `X-Forwarded-For` gracias a `--proxy-headers` (ver el Dockerfile)."""
    return peticion.client.host if peticion.client else None


class RegistroDePeticiones(BaseHTTPMiddleware):
    """Id de petición y una línea de acceso por cada una."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        recibido = request.headers.get(ENCABEZADO_ID_PETICION, "")
        id_peticion = recibido if _ID_ACEPTABLE.match(recibido) else uuid.uuid4().hex
        marca = id_peticion_actual.set(id_peticion)
        inicio = time.perf_counter()
        estado = 500
        try:
            respuesta = await call_next(request)
            estado = respuesta.status_code
            respuesta.headers[ENCABEZADO_ID_PETICION] = id_peticion
            return respuesta
        finally:
            nivel = logging.DEBUG if request.url.path in _RUTAS_DE_SONDEO else logging.INFO
            registro_de_acceso.log(
                nivel,
                "%s %s -> %s",
                request.method,
                request.url.path,
                estado,
                extra={
                    "evento": "peticion_atendida",
                    "metodo": request.method,
                    # Solo la ruta: la query string puede traer datos del titular.
                    "ruta": request.url.path,
                    "estado": estado,
                    "duracion_ms": round((time.perf_counter() - inicio) * 1000, 1),
                    "usuario_id": getattr(request.state, "usuario_id", None),
                    "ip": ip_de(request),
                },
            )
            id_peticion_actual.reset(marca)


# Swagger UI y ReDoc cargan su JavaScript de un CDN; una política que lo
# prohíbe las dejaría en blanco. El resto de la API solo devuelve JSON.
_RUTAS_DE_DOCUMENTACION = ("/docs", "/redoc")


class CabecerasDeSeguridad(BaseHTTPMiddleware):
    """Las cabeceras de seguridad que toda respuesta lleva."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        respuesta = await call_next(request)
        cabeceras = respuesta.headers
        # No adivinar el tipo de contenido: un JSON nunca se ejecuta como script.
        cabeceras.setdefault("X-Content-Type-Options", "nosniff")
        # Ninguna página de esta API se muestra dentro de un <iframe> ajeno.
        cabeceras.setdefault("X-Frame-Options", "DENY")
        cabeceras.setdefault("Referrer-Policy", "no-referrer")
        # Solo HTTPS durante un año. El navegador la ignora si llegó por HTTP,
        # así que en desarrollo no estorba.
        cabeceras.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if not request.url.path.startswith(_RUTAS_DE_DOCUMENTACION):
            cabeceras.setdefault(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
        if request.url.path.startswith("/api/"):
            # Datos de gasto de una persona: ningún proxy ni caché los guarda.
            cabeceras.setdefault("Cache-Control", "no-store")
        return respuesta
