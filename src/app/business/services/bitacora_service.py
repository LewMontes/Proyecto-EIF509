"""Bitácora de trazabilidad de una compra, en MongoDB.

Escribe en la colección `bitacora_compras` -mismo validador de 13 tipos de
evento que ya define `db/mongo/init/01_bitacora_compras.js` para el
Laboratorio 2 (`TIPOS_DE_EVENTO` de abajo es la misma lista, no una nueva)-
pero ahora desde la aplicación que corre de verdad, disparada por
`ConciliacionService` en vez de solo por el seed académico.

Este servicio decide **qué** se registra: valida que el tipo de evento exista
en el vocabulario cerrado, arma el documento del evento con su actor y su
número de secuencia, y decide que un fallo de Mongo no puede tumbar nada. El
**cómo** se guarda -la colección, el `upsert`, los errores de PyMongo- vive en
`BitacoraRepository`, igual que para el resto del sistema vive en la capa de
datos y no acá.

Nunca bloquea la conciliación en PostgreSQL: el repositorio devuelve `False`
en vez de propagar el error, y este servicio no hace nada con ese `False`. Es
el mismo trade-off que documenta ADR-002 -la bitácora **explica** lo que pasó,
no lo **decide**; ningún saldo ni ningún total del sistema depende de ella.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.data.repositories.bitacora_repository import BitacoraRepository

# Vocabulario cerrado, idéntico al validador de Mongo. Un tipo que no esté
# acá nunca debería intentar escribirse -si hiciera falta uno nuevo, primero
# se agrega ahí y aquí a la vez.
TIPOS_DE_EVENTO = (
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
)


@dataclass(frozen=True)
class Actor:
    """Quién provocó el evento: una persona, la ingesta, o una regla que se disparó sola."""

    tipo: str  # "TITULAR" | "SERVICIO" | "SISTEMA"
    usuario_id: int | None = None
    nombre: str | None = None


class BitacoraComprasService:
    """Agrega eventos a la bitácora de una compra, tolerando que Mongo no responda."""

    def __init__(self, repositorio: BitacoraRepository) -> None:
        self.bitacora = repositorio

    def registrar_evento(
        self,
        compra_id: int,
        usuario_id: int,
        estado_actual: str,
        tipo: str,
        datos: dict[str, Any],
        actor: Actor,
    ) -> None:
        """Agrega un evento a la bitácora de `compra_id`, creándola si es el primero.

        No propaga ninguna excepción: un Mongo caído o una escritura
        rechazada quedan solo en el log del repositorio, nunca revierten lo
        que ya se confirmó en PostgreSQL.

        `ValueError` por un tipo desconocido sí sube, y a propósito: eso no es
        un fallo de infraestructura sino un error de programación -alguien
        inventó un tipo de evento que el validador de Mongo va a rechazar de
        todas formas, y es mejor que reviente en la prueba que en producción.
        """
        if not self.bitacora.disponible:
            return
        if tipo not in TIPOS_DE_EVENTO:
            raise ValueError(f"Tipo de evento desconocido: {tipo!r}")

        ahora = datetime.now(UTC)
        evento = {
            "secuencia": self.bitacora.cantidad_de_eventos(compra_id) + 1,
            "tipo": tipo,
            "ocurrido_en": ahora,
            "actor": {"tipo": actor.tipo, "usuario_id": actor.usuario_id, "nombre": actor.nombre},
            "datos": datos,
        }
        self.bitacora.agregar_evento(compra_id, usuario_id, estado_actual, evento, ahora)

    def bitacora_de(self, compra_id: int) -> list[dict[str, Any]] | None:
        """Los eventos de una compra, en el orden en que ocurrieron. `None` si no hay Mongo
        disponible o la compra todavía no tiene ningún evento."""
        return self.bitacora.eventos_de(compra_id)
