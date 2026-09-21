"""Lector de las notificaciones de transaccion de BAC Credomatic.

BAC manda un mensaje de estructura fija: una etiqueta, dos puntos y el valor, una
linea por campo. Sobre ese formato las expresiones regulares son exactas y
gratis, asi que la extraccion no necesita un modelo de lenguaje. Lo que si lo
necesita es decidir a que categoria pertenece `WALMART SAN SEBASTIAN`, y eso
ocurre despues, sobre el resultado de este lector.

Dos rarezas del formato, ambas comprobadas contra un comprobante real:

- **Los acentos pueden venir rotos.** Si el comprobante se obtuvo imprimiendo el
  correo a PDF desde el navegador, la fuente incrustada pierde el mapa de los
  acentos y `Autorizacion` llega con un caracter de reemplazo en medio. Por eso
  cada patron lleva un comodin donde va la tilde, en vez de la letra.
- **La marca de la tarjeta es la etiqueta misma.** No hay un campo `Marca:`: la
  linea dice `AMEX: ***********4321`. La marca se lee de la etiqueta y los
  ultimos cuatro digitos del valor.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

CAMPOS_OBLIGATORIOS = ("comercio", "fecha", "ultimos_cuatro", "monto")

# Dominio real desde el que BAC manda sus notificaciones (confirmado contra un
# comprobante real: NotificacionBAC@baccredomatic.cr). Sirve para filtrar la
# bandeja y traer solo estos correos, antes de intentar parsear nada.
DOMINIO_REMITENTE_BAC = "baccredomatic.cr"

# El comodin `.` ocupa el lugar de la tilde: cubre tanto el acento correcto como
# el caracter de reemplazo que deja la impresion a PDF.
_COMERCIO = re.compile(r"^Comercio:[ \t]*(.+)$", re.MULTILINE)
_CIUDAD_PAIS = re.compile(r"^Ciudad y pa.s:[ \t]*(.+)$", re.MULTILINE)
_FECHA = re.compile(r"^Fecha:[ \t]*(.+)$", re.MULTILINE)
_TARJETA = re.compile(r"^(AMEX|VISA|MASTERCARD|MASTER CARD):\s*\*+(\d{4})\s*$", re.MULTILINE)
_AUTORIZACION = re.compile(r"Autorizaci.n:\s*(\w+)")
_REFERENCIA = re.compile(r"Referencia:\s*(\w+)")
_TIPO = re.compile(r"Tipo de Transacci.n:\s*(.+)")
_MONTO = re.compile(r"Monto:\s*([A-Z]{3})\s*([\d.,]+)")

_MESES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}  # fmt: skip

# "Ago 30, 2026 , 13:27" -- el espacio suelto antes de la segunda coma viene asi
# en el comprobante original; no es un error de transcripcion.
_FECHA_BAC = re.compile(
    r"([A-Za-z]{3})\w*\s+(\d{1,2}),?\s*(\d{4})\s*,?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?"
)


@dataclass(frozen=True)
class ComprobanteParseado:
    """Lo que el lector logro sacar de un comprobante.

    Es un resultado de lectura, no una entidad: no se guarda tal cual. El
    servicio de ingesta lo usa para resolver el comercio, emparejar el metodo de
    pago y armar la compra.
    """

    banco: str
    comercio: str | None
    ciudad: str | None
    pais: str | None
    fecha: datetime | None
    marca_tarjeta: str | None
    ultimos_cuatro: str | None
    autorizacion: str | None
    referencia: str | None
    tipo_transaccion: str | None
    moneda: str | None
    monto: Decimal | None
    confianza: float

    @property
    def es_compra(self) -> bool:
        """Una notificacion tambien puede ser una anulacion o un reverso.

        Solo las compras se convierten en gasto; las demas ajustan una compra que
        ya existe, y ese camino es trabajo del proceso de conciliacion.
        """
        return self.tipo_transaccion == "COMPRA"

    @property
    def es_confiable(self) -> bool:
        """Bajo 0.75 el comprobante no se convierte en compra solo: va a revision."""
        return self.confianza >= 0.75


def parsear_comprobante_bac(texto: str) -> ComprobanteParseado:
    """Lee una notificacion de BAC y devuelve sus campos.

    Nunca lanza excepcion por un campo ausente: devuelve el campo en `None` y lo
    refleja en la confianza. Un comprobante incompleto es un caso normal del
    negocio -va a revision manual-, no un error del programa.
    """
    comercio = _primer_grupo(_COMERCIO, texto)
    ciudad, pais = _partir_ciudad_y_pais(_primer_grupo(_CIUDAD_PAIS, texto))
    fecha = _leer_fecha(_primer_grupo(_FECHA, texto))
    marca, ultimos_cuatro = _leer_tarjeta(texto)
    moneda, monto = _leer_monto(texto)

    campos = {
        "comercio": comercio,
        "fecha": fecha,
        "ultimos_cuatro": ultimos_cuatro,
        "monto": monto,
    }
    encontrados = sum(1 for nombre in CAMPOS_OBLIGATORIOS if campos[nombre] is not None)

    return ComprobanteParseado(
        banco="BAC Credomatic",
        comercio=comercio,
        ciudad=ciudad,
        pais=pais,
        fecha=fecha,
        marca_tarjeta=marca,
        ultimos_cuatro=ultimos_cuatro,
        autorizacion=_primer_grupo(_AUTORIZACION, texto),
        referencia=_primer_grupo(_REFERENCIA, texto),
        tipo_transaccion=_normalizar(_primer_grupo(_TIPO, texto)),
        moneda=moneda,
        monto=monto,
        confianza=encontrados / len(CAMPOS_OBLIGATORIOS),
    )


def _primer_grupo(patron: re.Pattern[str], texto: str) -> str | None:
    coincidencia = patron.search(texto)
    return coincidencia.group(1).strip() if coincidencia else None


def _normalizar(valor: str | None) -> str | None:
    """Sube a mayusculas y quita acentos, para comparar sin sorpresas."""
    if valor is None:
        return None
    sin_acentos = unicodedata.normalize("NFKD", valor)
    return "".join(c for c in sin_acentos if not unicodedata.combining(c)).upper().strip()


def _partir_ciudad_y_pais(valor: str | None) -> tuple[str | None, str | None]:
    """`SAN JOSE, Costa Rica` -> ciudad y pais.

    Se parte por la ultima coma porque la ciudad puede llevar coma adentro.
    """
    if valor is None:
        return None, None
    if "," not in valor:
        return valor.strip(), None
    ciudad, pais = valor.rsplit(",", 1)
    return ciudad.strip(), pais.strip()


def _leer_tarjeta(texto: str) -> tuple[str | None, str | None]:
    coincidencia = _TARJETA.search(texto)
    if coincidencia is None:
        return None, None
    return coincidencia.group(1).replace(" ", "").upper(), coincidencia.group(2)


def _leer_monto(texto: str) -> tuple[str | None, Decimal | None]:
    """`CRC 7,870.00` -> moneda y monto exacto.

    La coma separa miles y el punto separa decimales. El monto se devuelve como
    Decimal: con punto flotante un reporte de gastos no cuadra por centimos.
    """
    coincidencia = _MONTO.search(texto)
    if coincidencia is None:
        return None, None
    moneda = coincidencia.group(1)
    try:
        return moneda, Decimal(coincidencia.group(2).replace(",", ""))
    except ArithmeticError:
        return moneda, None


def _leer_fecha(valor: str | None) -> datetime | None:
    """`Ago 30, 2026 , 13:27` -> datetime. El mes viene abreviado en espanol."""
    if valor is None:
        return None
    coincidencia = _FECHA_BAC.search(valor)
    if coincidencia is None:
        return None
    mes = _MESES.get(_normalizar(coincidencia.group(1)) or "")
    if mes is None:
        return None
    dia, anio, hora, minuto = (int(coincidencia.group(i)) for i in (2, 3, 4, 5))
    segundo = int(coincidencia.group(6) or 0)
    try:
        return datetime(anio, mes, dia, hora, minuto, segundo)
    except ValueError:
        return None
