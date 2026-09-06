"""Enumeraciones del dominio."""

from enum import StrEnum


class Moneda(StrEnum):
    """Monedas que el sistema reconoce. La base de calculo es el colon."""

    CRC = "CRC"
    USD = "USD"
    EUR = "EUR"


class ProveedorCorreo(StrEnum):
    """Buzones que el sistema sabe vincular y leer."""

    OUTLOOK = "OUTLOOK"
    GMAIL = "GMAIL"


class EstadoCuentaCorreo(StrEnum):
    """Ciclo de vida de un buzón vinculado."""

    ACTIVA = "ACTIVA"
    TOKEN_EXPIRADO = "TOKEN_EXPIRADO"
    DESVINCULADA = "DESVINCULADA"
    ERROR = "ERROR"


class EstadoPresupuesto(StrEnum):
    """Dónde va el gasto de una categoría respecto a su límite del mes.

    No se persiste: se calcula cada vez, comparando el límite guardado contra
    el consumo real del período. Ver `PresupuestoService.calcular_estado`.
    """

    EN_RANGO = "EN_RANGO"
    CERCA_DEL_LIMITE = "CERCA_DEL_LIMITE"
    EXCEDIDO = "EXCEDIDO"


class EstadoCompra(StrEnum):
    """Ciclo de vida de una compra. `CONCILIADA` no se edita, solo se anula."""

    BORRADOR = "BORRADOR"
    REGISTRADA = "REGISTRADA"
    CONCILIADA = "CONCILIADA"
    ANULADA = "ANULADA"


class OrigenCompra(StrEnum):
    """De dónde nació la compra."""

    MANUAL = "MANUAL"
    INGESTA_CORREO = "INGESTA_CORREO"
    FACTURA_XML = "FACTURA_XML"


class TipoMetodoPago(StrEnum):
    """Solo DEBITO/CREDITO llevan últimos cuatro dígitos -ver MetodoPago."""

    EFECTIVO = "EFECTIVO"
    DEBITO = "DEBITO"
    CREDITO = "CREDITO"
    SINPE_MOVIL = "SINPE_MOVIL"
    TRANSFERENCIA = "TRANSFERENCIA"


class CampoRegla(StrEnum):
    """Sobre qué texto se evalúa el patrón de una ReglaCategorizacion.

    Cerrado a propósito: si fuera texto libre, una regla podría apuntar a un
    campo inexistente y el motor de categorización fallaría en tiempo de
    ejecución en vez de al guardarla.
    """

    COMERCIO_NORMALIZADO = "COMERCIO_NORMALIZADO"
    DESCRIPCION_COMPRA = "DESCRIPCION_COMPRA"
    DESCRIPCION_LINEA = "DESCRIPCION_LINEA"
