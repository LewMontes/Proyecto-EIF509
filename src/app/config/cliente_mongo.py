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

Escribe en una base de Mongo distinta a la que siembra
`db/mongo/init/` para el Laboratorio 2 (ver la nota de `mongo_db` en
`settings.py`) -por eso, a diferencia del script de esa carpeta, esta
colección se asegura con el mismo validador acá mismo, en Python: no hay
ningún script `docker-entrypoint-initdb.d` que la cree para una base que
Mongo nunca inicializa sola.
"""

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.config.settings import obtener_configuracion

_cliente: MongoClient | None = None
_coleccion_asegurada = False

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


def obtener_coleccion_bitacora() -> Collection:
    """Entrega la colección `bitacora_compras` de la app, asegurando su validador."""
    global _cliente, _coleccion_asegurada
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
            # Sin Mongo disponible ahora mismo, se reintenta en la próxima
            # llamada -BitacoraComprasService igual tolera que la colección
            # no tenga validador puesto: la suya propia (TIPOS_DE_EVENTO) es
            # la que de verdad protege la escritura.
            pass

    return base["bitacora_compras"]


def cerrar_cliente_mongo() -> None:
    """Cierra el cliente compartido. Se llama al apagar la aplicación."""
    global _cliente, _coleccion_asegurada
    if _cliente is not None:
        _cliente.close()
        _cliente = None
    _coleccion_asegurada = False
