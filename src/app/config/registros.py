"""Registros estructurados: una línea JSON por evento, en la salida estándar.

Es el equivalente de configurar Logback con un *encoder* JSON en Spring Boot.
La aplicación no escribe archivos de log: en un contenedor, lo que sale por
`stdout` lo recoge la plataforma (Render, Docker, `docker compose logs`) y lo
deja buscable. Una línea JSON por evento es lo que esas herramientas filtran
sin tener que adivinar un formato de texto.

Cada línea trae siempre los mismos campos -`momento`, `nivel`, `registrador`,
`mensaje`- más el `id_peticion` de la petición que la produjo, y lo que el
código agregue con `extra={...}` (por ejemplo `evento`, `ruta`, `estado`).

**Nada sensible llega al registro.** Dos defensas, por si una falla:

1. Los registros de la aplicación nunca reciben cuerpos ni encabezados de la
   petición: la línea de acceso guarda la ruta sin la *query string*, y los
   eventos de seguridad guardan qué pasó, no con qué credenciales.
2. Si aun así un campo `extra` se llama como algo secreto -`contrasena`,
   `token`, `authorization`...- el formateador lo reemplaza por
   `[REDACTADO]` antes de escribir.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# El id de la petición en curso. Un ContextVar y no una variable global: cada
# petición -cada hilo del pool de uvicorn- ve el suyo.
id_peticion_actual: ContextVar[str | None] = ContextVar("id_peticion_actual", default=None)

REDACTADO = "[REDACTADO]"

# Partes de nombre de campo que nunca se escriben tal cual.
_CAMPOS_SECRETOS = (
    "contrasena",
    "password",
    "secreto",
    "secret",
    "token",
    "authorization",
    "cookie",
    "clave",
)

# Los atributos que todo `LogRecord` trae de fábrica. Lo que no está acá llegó
# por `extra={...}` y va a la línea JSON como campo propio.
#
# `color_message` lo agrega uvicorn: es el mismo mensaje con códigos de color
# ANSI para una terminal, ruido en una línea JSON.
_ATRIBUTOS_ESTANDAR = frozenset(
    vars(logging.LogRecord("", logging.INFO, "", 0, "", None, None)).keys()
) | {"message", "asctime", "taskName", "color_message"}


def _es_secreto(nombre: str) -> bool:
    nombre = nombre.lower()
    return any(parte in nombre for parte in _CAMPOS_SECRETOS)


class FormatoJson(logging.Formatter):
    """Convierte cada `LogRecord` en una sola línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        linea: dict[str, Any] = {
            "momento": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "nivel": record.levelname,
            "registrador": record.name,
            "mensaje": record.getMessage(),
        }
        for nombre, valor in vars(record).items():
            if nombre in _ATRIBUTOS_ESTANDAR or nombre.startswith("_"):
                continue
            if nombre == "id_peticion" and valor is None:
                continue
            linea[nombre] = REDACTADO if _es_secreto(nombre) else valor
        if record.exc_info:
            linea["excepcion"] = self.formatException(record.exc_info)
        return json.dumps(linea, ensure_ascii=False, default=str)


_fabrica_original = logging.getLogRecordFactory()


def _fabrica_con_id_de_peticion(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Crea cada `LogRecord` con el `id_peticion` de la petición en curso.

    Se estampa al **crear** el registro y no al formatearlo: así lo lleva
    también si otro manejador lo escribe más tarde, cuando la petición ya
    terminó y el ContextVar volvió a vacío.
    """
    registro = _fabrica_original(*args, **kwargs)
    registro.id_peticion = id_peticion_actual.get()
    return registro


class _ManejadorDeGastonomo(logging.StreamHandler):
    """El manejador que instala `configurar_registros`.

    Una clase propia solo para poder reconocerlo: configurar dos veces -cada
    `crear_app()` de las pruebas- reemplaza el anterior en vez de duplicar las
    líneas, y no toca los manejadores que otro instaló (el de `caplog`).
    """


def configurar_registros(nivel: str = "INFO") -> None:
    """Deja todos los registros del proceso saliendo como JSON por `stdout`.

    Incluye los de uvicorn: sin esto, sus líneas de arranque y de error
    saldrían en texto plano, mezcladas con las JSON. El registro de acceso de
    uvicorn se silencia porque `RegistroDePeticiones` ya escribe uno por
    petición, y con más datos (duración, id de la petición, titular).
    """
    logging.setLogRecordFactory(_fabrica_con_id_de_peticion)
    manejador = _ManejadorDeGastonomo(sys.stdout)
    manejador.setFormatter(FormatoJson())

    raiz = logging.getLogger()
    for anterior in [h for h in raiz.handlers if isinstance(h, _ManejadorDeGastonomo)]:
        raiz.removeHandler(anterior)
    raiz.addHandler(manejador)
    raiz.setLevel(nivel.upper())

    for nombre in ("uvicorn", "uvicorn.error"):
        registrador = logging.getLogger(nombre)
        registrador.handlers.clear()
        registrador.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx escribe en INFO la URL completa de cada petición que hace, y la del
    # Banco Central lleva el token de suscripción en la query string.
    for nombre in ("httpx", "httpcore"):
        logging.getLogger(nombre).setLevel(logging.WARNING)
