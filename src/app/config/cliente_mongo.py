"""Cliente de Mongo compartido para la bitácora de trazabilidad de compras.

Mismo criterio que `cliente_http.py`: un solo cliente para toda la
aplicación, creado la primera vez que se pide. `MongoClient` ya administra
su propio pool de conexiones y es seguro compartirlo entre hilos -no hace
falta uno por petición, a diferencia de la sesión de SQLAlchemy.

La conexión es perezosa: `MongoClient(...)` no toca la red hasta la primera
operación real, así que crear el cliente aquí nunca falla por sí solo aunque
Mongo esté apagado. Quien de verdad necesita tolerar que Mongo no responda
es `BitacoraComprasService`, que envuelve cada escritura en su propio
`try/except` -ver la nota en ese archivo.

**Cuando Mongo no responde, se deja de insistir por un rato.** Cada operación
contra un Mongo apagado espera sus 3 segundos de `serverSelectionTimeoutMS`
antes de rendirse, y registrar una compra escribe entre cinco y diez eventos:
sin este corte, una sola petición a la API tardaba más de medio minuto solo en
esperar a un servidor que no estaba. Ahora, al primer fallo se anota hasta
cuándo no vale la pena volver a probar (`_REINTENTAR_TRAS_SEGUNDOS`), y hasta
entonces `obtener_coleccion_bitacora` devuelve `None` -que `BitacoraRepository`
trata como «no hay bitácora»-. Pasado ese tiempo se vuelve a intentar sola, así
que levantar Mongo después no exige reiniciar la aplicación.

Escribe en una base de Mongo distinta a la que siembra
`db/mongo/init/` para el Laboratorio 2 (ver la nota de `mongo_db` en
`settings.py`) -por eso, a diferencia del script de esa carpeta, esta
colección se asegura con el mismo validador acá mismo, en Python: no hay
ningún script `docker-entrypoint-initdb.d` que la cree para una base que
Mongo nunca inicializa sola.
"""

import time

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.config.settings import obtener_configuracion

_cliente: MongoClient | None = None
_coleccion_asegurada = False

# Cuánto se espera antes de volver a probar un Mongo que no respondió, y hasta
# qué instante (del reloj monotónico) dura esa espera.
_REINTENTAR_TRAS_SEGUNDOS = 30.0
_sin_mongo_hasta = 0.0

# Mismo vocabulario cerrado que db/mongo/init/01_bitacora_compras.js y
# business/services/bitacora_service.py -las tres listas tienen que
# coincidir; si un tipo de evento nuevo hace falta, se agrega a las tres.
_VALIDADOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Bitácora de trazabilidad de una compra",
        "required": [
            "compra_id",
            "usuario_id",
            "estado_actual",
            "abierta_en",
            "actualizada_en",
            "eventos",
        ],
        "additionalProperties": False,
        "properties": {
            "_id": {"bsonType": "objectId"},
            # ["int", "long"]: pymongo serializa un `int` de Python que cabe
            # en 32 bits como BSON int32, no int64 -a diferencia de
            # `NumberLong(...)` que usa a propósito el seed académico
            # (db/mongo/init/) para calzar con el BIGINT de Postgres. Acá no
            # hay ninguna razón real para forzar int64: se aceptan los dos
            # anchos en vez de arriesgar que cada escritura real falle la
            # validación (fue exactamente lo que pasó la primera vez que
            # `ConciliacionService` escribió acá con `compra_id`/`usuario_id`
            # como `int` planos).
            "compra_id": {"bsonType": ["int", "long"]},
            "usuario_id": {"bsonType": ["int", "long"]},
            "estado_actual": {
                "bsonType": "string",
                "enum": ["BORRADOR", "REGISTRADA", "CONCILIADA", "ANULADA"],
            },
            "abierta_en": {"bsonType": "date"},
            "actualizada_en": {"bsonType": "date"},
            "eventos": {
                "bsonType": "array",
                "minItems": 1,
                "maxItems": 200,
                "items": {
                    "bsonType": "object",
                    "required": ["secuencia", "tipo", "ocurrido_en", "actor"],
                    "additionalProperties": False,
                    "properties": {
                        "secuencia": {"bsonType": "int", "minimum": 1},
                        "tipo": {
                            "bsonType": "string",
                            "enum": [
                                "INGESTA_RECIBIDA",
                                "PARSEO_COMPROBANTE",
                                "EMPAREJAMIENTO_METODO_PAGO",
                                "RESOLUCION_COMERCIO",
                                "CATEGORIZACION_AUTOMATICA",
                                "CORRECCION_MANUAL",
                                "DESGLOSE_MANUAL",
                                "CONVERSION_MONEDA",
                                "IMPACTO_PRESUPUESTO",
                                "ALERTA_PRESUPUESTO",
                                "CAMBIO_ESTADO",
                                "REVISION_REQUERIDA",
                                "ANULACION",
                            ],
                        },
                        "ocurrido_en": {"bsonType": "date"},
                        "actor": {
                            "bsonType": "object",
                            "required": ["tipo"],
                            "properties": {
                                "tipo": {
                                    "bsonType": "string",
                                    "enum": ["TITULAR", "SERVICIO", "SISTEMA"],
                                },
                                "usuario_id": {"bsonType": ["int", "long", "null"]},
                                "nombre": {"bsonType": ["string", "null"]},
                            },
                        },
                        "datos": {"bsonType": "object"},
                    },
                },
            },
        },
    }
}


def marcar_mongo_caido() -> None:
    """Anota que Mongo no respondió: no se lo vuelve a probar por un rato."""
    global _sin_mongo_hasta
    _sin_mongo_hasta = time.monotonic() + _REINTENTAR_TRAS_SEGUNDOS


def obtener_coleccion_bitacora() -> Collection | None:
    """Entrega la colección `bitacora_compras` de la app, asegurando su validador.

    `None` si Mongo no respondió hace poco: quien la recibe trabaja sin
    bitácora en vez de esperar otra vez a un servidor que no está.
    """
    global _cliente, _coleccion_asegurada
    if time.monotonic() < _sin_mongo_hasta:
        return None
    if _cliente is None:
        configuracion = obtener_configuracion()
        _cliente = MongoClient(configuracion.mongo_url, serverSelectionTimeoutMS=3000)
    configuracion = obtener_configuracion()
    base = _cliente[configuracion.mongo_db]

    if not _coleccion_asegurada:
        try:
            if "bitacora_compras" not in base.list_collection_names():
                base.create_collection(
                    "bitacora_compras",
                    validator=_VALIDADOR,
                    validationLevel="strict",
                    validationAction="error",
                )
            else:
                base.command(
                    "collMod",
                    "bitacora_compras",
                    validator=_VALIDADOR,
                    validationLevel="strict",
                    validationAction="error",
                )
            _coleccion_asegurada = True
        except PyMongoError:
            # Sin Mongo disponible ahora mismo: se trabaja sin bitácora y se
            # reintenta cuando pase la espera.
            marcar_mongo_caido()
            return None

    return base["bitacora_compras"]


def cerrar_cliente_mongo() -> None:
    """Cierra el cliente compartido. Se llama al apagar la aplicación."""
    global _cliente, _coleccion_asegurada, _sin_mongo_hasta
    if _cliente is not None:
        _cliente.close()
        _cliente = None
    _coleccion_asegurada = False
    _sin_mongo_hasta = 0.0
