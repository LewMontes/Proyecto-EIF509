"""Tipo de cambio de referencia (colones/dólares), del Banco Central de Costa Rica.

Hay dos caminos hasta el mismo dato oficial, y este servicio usa el que esté
disponible:

1. **El BCCR directamente**, por su "Servicio Web de Indicadores Económicos"
   (https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx),
   un servicio SOAP/ASMX clásico que también acepta invocación por HTTP GET.
   Igual que Outlook y Gmail hace falta una suscripción propia -acá no es
   OAuth2, es un correo y un token que el BCCR entrega al confirmar la
   suscripción, gratis (ver GASTONOMO_BCCR_CORREO/TOKEN en `settings.py` y la
   sección de conversión de moneda del README).

2. **El Ministerio de Hacienda** (https://api.hacienda.go.cr/indicadores/tc),
   que republica ese mismo tipo de cambio de referencia del BCCR en JSON, sin
   suscripción ni token. Es el respaldo, y solo sirve para el día de hoy: ese
   endpoint no acepta fechas históricas.

El respaldo no es un capricho: al escribirse esto, todo el subsistema
`gee.bccr.fi.cr/Indicadores/` llevaba días devolviendo `HTTP 503` -incluida la
página donde uno se suscribe, así que ni siquiera se podía sacar el token. Sin
el respaldo, la conversión de moneda quedaba muerta por una caída ajena. Se
prefiere el BCCR cuando hay credenciales y responde; Hacienda solo entra
cuando el primero no está disponible.

Los nombres de parámetro (`Indicador`, `FechaInicio`, `FechaFinal`,
`Nombre`, `SubNiveles`, `CorreoElectronico`, `Token`) están tomados de la
página de ayuda que el propio ASMX genera para el método, que documenta
literalmente la invocación por HTTP GET. Conviene no confundirlos con
`tcIndicador`, `tcCorreo`, `tcToken` y compañía, que circulan en
documentación de terceros: esos son los nombres internos de la
implementación en VB.NET del BCCR, no los que acepta el lado HTTP.

Invocado por GET, el método no devuelve el XML de los indicadores
directamente: lo envuelve como texto escapado dentro de un elemento
`<string xmlns="http://ws.sdde.bccr.fi.cr">`. Por eso `_valor_mas_reciente`
reintenta parseando el texto interno como un segundo documento.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx

from app.business.errors import ErrorDeProveedorExterno
from app.config.settings import Configuracion

_URL_SERVICIO = (
    "https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx"
    "/ObtenerIndicadoresEconomicosXML"
)
_URL_HACIENDA = "https://api.hacienda.go.cr/indicadores/tc"
_INDICADOR_COMPRA = 317
_INDICADOR_VENTA = 318
_DIAS_DE_MARGEN = 7  # cubre un fin de semana largo o feriado sin dato publicado


@dataclass(frozen=True)
class TipoDeCambio:
    """Tipo de cambio de referencia del colón contra el dólar, para un día."""

    fecha: date
    compra: Decimal
    venta: Decimal


MONEDAS_CONVERTIBLES = ("CRC", "USD")


def convertir(monto: Decimal, desde: str, hacia: str, venta: Decimal) -> Decimal:
    """Pasa un monto de una moneda a la otra, redondeado a dos decimales.

    Recibe la tasa suelta y no un `TipoDeCambio` porque quien llama no siempre
    tiene uno completo: un comprobante guarda solo la tasa de venta con la que
    se selló, no el par compra/venta de ese día.

    Se usa el tipo de cambio de **venta** en las dos direcciones, no venta
    para una y compra para la otra. La razón es que esto convierte *gastos*:
    la pregunta que responde es "cuánto me habría costado esto en la otra
    moneda", y para eso la referencia es siempre lo que cuesta comprar
    dólares. Usar dos tasas distintas según la dirección haría que convertir
    de ida y vuelta no diera el mismo número, que es peor que ser
    ligeramente conservador.

    Una moneda que no sea CRC ni USD se devuelve sin tocar: no hay tasa para
    ella, e inventar una sería peor que no convertir.
    """
    if desde == hacia or desde not in MONEDAS_CONVERTIBLES or hacia not in MONEDAS_CONVERTIBLES:
        return monto
    convertido = monto * venta if hacia == "CRC" else monto / venta
    return convertido.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class TipoCambioService:
    """Consulta el tipo de cambio de referencia del BCCR, con caché en memoria por fecha.

    El tipo de cambio no cambia dentro del mismo día -el BCCR publica el
    del día siguiente después de las 5:30pm-, así que pedirlo de nuevo
    para la misma fecha no debería volver a tocar la red. La caché es de
    proceso, no de base de datos: es información pública y de referencia,
    no algo que valga la pena persistir por usuario.
    """

    def __init__(self, cliente: httpx.Client, configuracion: Configuracion) -> None:
        self._cliente = cliente
        self._correo = configuracion.bccr_correo
        self._token = configuracion.bccr_token
        self._cache: dict[date, TipoDeCambio] = {}

    @property
    def configurado(self) -> bool:
        """Si hay credenciales del BCCR -sin ellas solo queda el respaldo de Hacienda."""
        return bool(self._correo and self._token)

    def obtener(self, fecha: date | None = None) -> TipoDeCambio:
        """El tipo de cambio de referencia más reciente hasta la fecha pedida (hoy, por defecto).

        Intenta primero el BCCR y cae a Hacienda si no está disponible. El
        respaldo solo entra para el día de hoy: su endpoint no acepta fechas
        históricas, y devolver el valor de hoy etiquetado con otra fecha sería
        mentir sobre el dato.

        Si los dos fallan, el error explica qué pasó con cada uno -son dos
        causas muy distintas (falta suscribirse / el proveedor está caído) y
        con un solo mensaje genérico no habría forma de saber cuál es.
        """
        fecha = fecha or date.today()
        if fecha in self._cache:
            return self._cache[fecha]

        resultado, motivos = self._consultar(fecha)
        if resultado is None:
            raise ErrorDeProveedorExterno(
                "No se pudo obtener el tipo de cambio de referencia. " + " ".join(motivos)
            )
        self._cache[fecha] = resultado
        return resultado

    def _consultar(self, fecha: date) -> tuple[TipoDeCambio | None, list[str]]:
        motivos: list[str] = []

        if self.configurado:
            try:
                return self._del_banco_central(fecha), motivos
            except ErrorDeProveedorExterno as error:
                motivos.append(f"Banco Central: {error}")
        else:
            motivos.append(
                "Banco Central: falta GASTONOMO_BCCR_CORREO y/o GASTONOMO_BCCR_TOKEN "
                "(ver la sección de conversión de moneda del README para suscribirse)."
            )

        if fecha != date.today():
            motivos.append(
                "Hacienda: solo publica el tipo de cambio del día, no el de una fecha pasada."
            )
            return None, motivos

        try:
            return self._de_hacienda(), motivos
        except ErrorDeProveedorExterno as error:
            motivos.append(f"Hacienda: {error}")
        return None, motivos

    def _pedir(self, url: str, params: dict | None = None) -> httpx.Response:
        """Hace la petición traduciendo cualquier fallo de red a un error del dominio.

        Sin esto, un timeout o un DNS caído salen como `httpx.ReadTimeout` -una
        excepción de la librería HTTP, no del dominio- y se escapan de todos los
        `except ErrorDeProveedorExterno` que la aplicación tiene puestos
        justamente para tolerar que este servicio falle. El síntoma real fue una
        sincronización de correo caída entera con un 500 porque Hacienda tardó
        en responder, cuando el tipo de cambio ahí es solo un extra.
        """
        try:
            return self._cliente.get(url, params=params)
        except httpx.HTTPError as error:
            raise ErrorDeProveedorExterno(f"no respondió ({type(error).__name__}).") from error

    def _del_banco_central(self, fecha: date) -> TipoDeCambio:
        """Consulta un rango de días y se queda con el valor más reciente.

        El rango de `_DIAS_DE_MARGEN` días no es por gusto: el BCCR no publica
        tipo de cambio los fines de semana ni los feriados, así que pedir
        exactamente un sábado devolvería "Nothing".
        """
        desde = fecha - timedelta(days=_DIAS_DE_MARGEN)
        return TipoDeCambio(
            fecha=fecha,
            compra=self._ultimo_valor(_INDICADOR_COMPRA, desde, fecha),
            venta=self._ultimo_valor(_INDICADOR_VENTA, desde, fecha),
        )

    def _de_hacienda(self) -> TipoDeCambio:
        """El mismo tipo de cambio de referencia, republicado por Hacienda en JSON.

        La fecha que se devuelve es la que reporta Hacienda, no la que se
        pidió: un lunes temprano puede seguir publicando el valor del viernes,
        y quien muestre el dato tiene que poder decir de qué día es.
        """
        respuesta = self._pedir(_URL_HACIENDA)
        if respuesta.status_code >= 400:
            raise ErrorDeProveedorExterno(
                f"respondió HTTP {respuesta.status_code}: {respuesta.text[:200]}"
            )
        try:
            dolar = respuesta.json()["dolar"]
            return TipoDeCambio(
                fecha=date.fromisoformat(str(dolar["venta"]["fecha"])[:10]),
                compra=Decimal(str(dolar["compra"]["valor"])),
                venta=Decimal(str(dolar["venta"]["valor"])),
            )
        except (ValueError, KeyError, TypeError, InvalidOperation) as error:
            raise ErrorDeProveedorExterno(
                f"devolvió una respuesta que no se pudo interpretar ({error})."
            ) from error

    def _ultimo_valor(self, indicador: int, desde: date, hasta: date) -> Decimal:
        respuesta = self._pedir(
            _URL_SERVICIO,
            {
                "Indicador": indicador,
                "FechaInicio": desde.strftime("%d/%m/%Y"),
                "FechaFinal": hasta.strftime("%d/%m/%Y"),
                "Nombre": "Gastonomo",
                # "N": sin subniveles. El tipo de cambio no los tiene, y
                # pedirlos traería filas de desglose que acá no sirven.
                "SubNiveles": "N",
                "CorreoElectronico": self._correo,
                "Token": self._token,
            },
        )
        if respuesta.status_code >= 400:
            raise ErrorDeProveedorExterno(
                f"El Banco Central rechazó la solicitud de tipo de cambio "
                f"(HTTP {respuesta.status_code}): {respuesta.text[:300]}"
            )
        return self._valor_mas_reciente(respuesta.text)

    def _valor_mas_reciente(self, xml_crudo: str) -> Decimal:
        try:
            raiz = ElementTree.fromstring(xml_crudo)
        except ElementTree.ParseError as error:
            raise ErrorDeProveedorExterno(
                "El Banco Central devolvió una respuesta que no se pudo leer como XML."
            ) from error

        # Invocado por HTTP GET (no SOAP puro), ObtenerIndicadoresEconomicosXML
        # puede anidar el XML de verdad como texto escapado dentro de un
        # elemento contenedor. Si el primer parseo no encuentra nada, se
        # reintenta con el texto interno como un segundo documento XML.
        valores = raiz.findall(".//NUM_VALOR")
        if not valores and raiz.text and "<" in raiz.text:
            try:
                interior = ElementTree.fromstring(raiz.text)
                valores = interior.findall(".//NUM_VALOR")
            except ElementTree.ParseError:
                valores = []

        if not valores or not valores[-1].text:
            raise ErrorDeProveedorExterno(
                "El Banco Central no devolvió ningún valor de tipo de cambio para ese rango "
                "de fechas -puede que el rango consultado no tenga ningún día hábil."
            )
        try:
            return Decimal(valores[-1].text.strip())
        except InvalidOperation as error:
            raise ErrorDeProveedorExterno(
                f"El Banco Central devolvió un valor de tipo de cambio no numérico: "
                f"{valores[-1].text!r}"
            ) from error
