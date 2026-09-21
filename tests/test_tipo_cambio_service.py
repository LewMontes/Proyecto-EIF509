"""El servicio de tipo de cambio, contra un Banco Central simulado.

`httpx.MockTransport` intercepta la petición antes de que salga a la red, así
que estas pruebas no dependen de que el BCCR esté disponible. Lo que no
pueden hacer es confirmar que el BCCR de verdad acepte lo que se le manda:
para eso hace falta el servicio en vivo y credenciales reales.

Lo que sí hacen es fijar el contrato documentado -nombres de parámetro y
formato de respuesta- tomado de la página de ayuda que el propio ASMX
genera para `ObtenerIndicadoresEconomicosXML`. Si alguien cambia esos
nombres por los `tcIndicador`/`tcCorreo`/`tcToken` que circulan en
documentación de terceros (los nombres internos de VB.NET del BCCR, no los
del lado HTTP), estas pruebas se caen.
"""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.business.errors import ErrorDeProveedorExterno
from app.business.services.tipo_cambio_service import (
    TipoCambioService,
    convertir,
)
from app.config.settings import Configuracion


def _configuracion(
    *, correo: str = "titular@ejemplo.cr", token: str = "token-de-prueba"
) -> Configuracion:
    return Configuracion(
        nombre_aplicacion="Gastonomo",
        version="0.1.0",
        url_base_datos="sqlite://",
        microsoft_client_id="",
        microsoft_client_secret="",
        microsoft_tenant="",
        microsoft_redirect_uri="",
        google_client_id="",
        google_client_secret="",
        google_redirect_uri="",
        google_login_redirect_uri="",
        clave_cifrado_tokens="clave-no-usada-en-estas-pruebas",
        origenes_permitidos=[],
        bccr_correo=correo,
        bccr_token=token,
        demo_correo="",
        demo_contrasena="",
    )


def _xml_de(*valores: str) -> str:
    filas = "".join(
        f"<INGC011_CAT_INDICADORECONOMIC><NUM_VALOR>{v}</NUM_VALOR></INGC011_CAT_INDICADORECONOMIC>"
        for v in valores
    )
    return f"<Datos_de_Indicador_Economico>{filas}</Datos_de_Indicador_Economico>"


def _respuesta_envuelta(xml_interno: str) -> str:
    """Como responde de verdad el ASMX invocado por GET: el XML va escapado adentro.

    El método no devuelve el XML de los indicadores como documento propio,
    sino como el *texto* de un elemento `<string>`. Es lo que obliga al
    servicio a reintentar el parseo sobre el contenido interno.
    """
    escapado = xml_interno.replace("<", "&lt;").replace(">", "&gt;")
    return f'<?xml version="1.0" encoding="utf-8"?><string xmlns="http://ws.sdde.bccr.fi.cr">{escapado}</string>'


def _bccr_simulado(peticion: httpx.Request) -> httpx.Response:
    indicador = peticion.url.params.get("Indicador")
    assert peticion.url.params.get("CorreoElectronico") == "titular@ejemplo.cr"
    assert peticion.url.params.get("Token") == "token-de-prueba"
    if indicador == "317":
        return httpx.Response(200, text=_xml_de("519.80", "520.50"))
    if indicador == "318":
        return httpx.Response(200, text=_xml_de("523.10", "524.00"))
    raise AssertionError(f"indicador inesperado en la prueba: {indicador}")


@pytest.fixture
def servicio() -> TipoCambioService:
    cliente = httpx.Client(transport=httpx.MockTransport(_bccr_simulado))
    return TipoCambioService(cliente, _configuracion())


def test_obtiene_compra_y_venta_y_se_queda_con_el_ultimo_valor_del_rango(
    servicio: TipoCambioService,
) -> None:
    """Del rango de _DIAS_DE_MARGEN días, el último valor es el más reciente."""
    tipo_de_cambio = servicio.obtener(date(2026, 9, 2))

    assert tipo_de_cambio.fecha == date(2026, 9, 2)
    assert tipo_de_cambio.compra == Decimal("520.50")
    assert tipo_de_cambio.venta == Decimal("524.00")


def test_manda_exactamente_los_parametros_que_documenta_el_banco_central() -> None:
    """Fija el contrato HTTP del BCCR, tal como lo documenta el propio servicio.

    Los siete parámetros son obligatorios: el BCCR responde "Nothing" -no un
    error- si falta alguno, así que un nombre mal escrito no se manifiesta
    como un fallo claro sino como "no hay tipo de cambio", que es mucho más
    difícil de diagnosticar. De ahí que valga la pena fijarlos acá.
    """
    capturadas: list[httpx.Request] = []

    def _capturar(peticion: httpx.Request) -> httpx.Response:
        capturadas.append(peticion)
        return httpx.Response(200, text=_xml_de("520.50"))

    cliente = httpx.Client(transport=httpx.MockTransport(_capturar))
    servicio = TipoCambioService(cliente, _configuracion())

    servicio.obtener(date(2026, 9, 2))

    url = capturadas[0].url
    assert url.path.endswith("/wsindicadoreseconomicos.asmx/ObtenerIndicadoresEconomicosXML")
    assert dict(url.params) == {
        "Indicador": "317",
        "FechaInicio": "26/08/2026",
        "FechaFinal": "02/09/2026",
        "Nombre": "Gastonomo",
        "SubNiveles": "N",
        "CorreoElectronico": "titular@ejemplo.cr",
        "Token": "token-de-prueba",
    }
    assert dict(capturadas[1].url.params)["Indicador"] == "318", "el segundo pide la venta"


def test_lee_el_valor_aunque_venga_envuelto_en_el_elemento_string() -> None:
    """Es la forma real de la respuesta del ASMX por GET, no un caso de borde."""

    def _envuelto(peticion: httpx.Request) -> httpx.Response:
        indicador = peticion.url.params.get("Indicador")
        interno = _xml_de("519.80", "520.50" if indicador == "317" else "524.00")
        return httpx.Response(200, text=_respuesta_envuelta(interno))

    cliente = httpx.Client(transport=httpx.MockTransport(_envuelto))
    servicio = TipoCambioService(cliente, _configuracion())

    tipo_de_cambio = servicio.obtener(date(2026, 9, 2))

    assert tipo_de_cambio.compra == Decimal("520.50")
    assert tipo_de_cambio.venta == Decimal("524.00")


def test_una_segunda_llamada_a_la_misma_fecha_no_vuelve_a_tocar_la_red() -> None:
    peticiones: list[httpx.Request] = []

    def _contador(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        indicador = peticion.url.params.get("Indicador")
        return httpx.Response(200, text=_xml_de("520.50" if indicador == "317" else "524.00"))

    cliente = httpx.Client(transport=httpx.MockTransport(_contador))
    servicio = TipoCambioService(cliente, _configuracion())

    servicio.obtener(date(2026, 9, 2))
    servicio.obtener(date(2026, 9, 2))

    assert len(peticiones) == 2, "compra y venta se piden una vez cada una, no cuatro"


_JSON_DE_HACIENDA = {
    "dolar": {
        "venta": {"fecha": "2026-09-02", "valor": 451.72},
        "compra": {"fecha": "2026-09-02", "valor": 445.58},
    }
}


def _hacienda_simulada(peticion: httpx.Request) -> httpx.Response:
    if "hacienda.go.cr" in peticion.url.host:
        return httpx.Response(200, json=_JSON_DE_HACIENDA)
    return httpx.Response(503, text="Service Unavailable")


def test_sin_credenciales_del_bccr_cae_al_respaldo_de_hacienda() -> None:
    """Hacienda republica el mismo dato del BCCR y no pide suscripción."""
    cliente = httpx.Client(transport=httpx.MockTransport(_hacienda_simulada))
    servicio = TipoCambioService(cliente, _configuracion(correo="", token=""))

    assert servicio.configurado is False
    tipo_de_cambio = servicio.obtener(date.today())

    assert tipo_de_cambio.compra == Decimal("445.58")
    assert tipo_de_cambio.venta == Decimal("451.72")
    assert tipo_de_cambio.fecha == date(2026, 9, 2), "la fecha es la que reporta Hacienda"


def test_si_el_banco_central_esta_caido_se_usa_hacienda() -> None:
    """Es exactamente el caso que motivó el respaldo: el BCCR devolviendo 503."""
    cliente = httpx.Client(transport=httpx.MockTransport(_hacienda_simulada))
    servicio = TipoCambioService(cliente, _configuracion())

    assert servicio.configurado is True
    assert servicio.obtener(date.today()).venta == Decimal("451.72")


def test_con_el_banco_central_disponible_no_se_consulta_hacienda() -> None:
    """El BCCR es la fuente primaria; el respaldo solo entra si la primera falla."""
    consultadas: list[str] = []

    def _registrando(peticion: httpx.Request) -> httpx.Response:
        consultadas.append(peticion.url.host)
        return _bccr_simulado(peticion)

    cliente = httpx.Client(transport=httpx.MockTransport(_registrando))
    servicio = TipoCambioService(cliente, _configuracion())

    servicio.obtener(date.today())

    assert set(consultadas) == {"gee.bccr.fi.cr"}


def test_una_fecha_pasada_sin_el_bccr_no_devuelve_el_valor_de_hoy() -> None:
    """Hacienda solo publica el del día: usarlo para otra fecha seria inventar el dato."""
    cliente = httpx.Client(transport=httpx.MockTransport(_hacienda_simulada))
    servicio = TipoCambioService(cliente, _configuracion(correo="", token=""))

    with pytest.raises(ErrorDeProveedorExterno, match="fecha pasada"):
        servicio.obtener(date(2020, 3, 15))


def test_si_fallan_las_dos_fuentes_el_error_explica_ambas(servicio: TipoCambioService) -> None:
    def _todo_falla(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    servicio._cliente = httpx.Client(transport=httpx.MockTransport(_todo_falla))  # type: ignore[attr-defined]

    with pytest.raises(ErrorDeProveedorExterno) as error:
        servicio.obtener(date.today())

    assert "Banco Central" in str(error.value)
    assert "Hacienda" in str(error.value)


def test_una_respuesta_sin_ningun_valor_da_error_de_proveedor_externo() -> None:
    def _vacio(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<Datos_de_Indicador_Economico></Datos_de_Indicador_Economico>"
        )

    cliente = httpx.Client(transport=httpx.MockTransport(_vacio))
    servicio = TipoCambioService(cliente, _configuracion())

    with pytest.raises(ErrorDeProveedorExterno):
        servicio.obtener(date(2026, 9, 2))


def test_una_respuesta_que_no_es_xml_valido_da_error_de_proveedor_externo() -> None:
    def _basura(peticion: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="esto no es XML")

    cliente = httpx.Client(transport=httpx.MockTransport(_basura))
    servicio = TipoCambioService(cliente, _configuracion())

    with pytest.raises(ErrorDeProveedorExterno):
        servicio.obtener(date(2026, 9, 2))


def test_convertir_usa_la_venta_en_las_dos_direcciones() -> None:
    """Convertir de ida y vuelta tiene que volver al mismo número.

    Si se usara venta para un lado y compra para el otro, pasar 100 dólares a
    colones y de vuelta a dólares daría menos de 100 -una fuga silenciosa en
    cada conversión.
    """
    tasa = Decimal("451.72")

    en_colones = convertir(Decimal("100.00"), "USD", "CRC", tasa)
    de_vuelta = convertir(en_colones, "CRC", "USD", tasa)

    assert en_colones == Decimal("45172.00")
    assert de_vuelta == Decimal("100.00")


def test_convertir_a_la_misma_moneda_no_toca_el_monto() -> None:
    tasa = Decimal("451.72")

    assert convertir(Decimal("7600.00"), "CRC", "CRC", tasa) == Decimal("7600.00")


def test_convertir_una_moneda_sin_tasa_la_deja_como_esta() -> None:
    """Inventar una tasa para el euro seria peor que no convertir."""
    tasa = Decimal("451.72")

    assert convertir(Decimal("50.00"), "EUR", "CRC", tasa) == Decimal("50.00")


def test_convertir_redondea_a_dos_decimales() -> None:
    tasa = Decimal("451.72")

    assert convertir(Decimal("6.00"), "USD", "CRC", tasa) == Decimal("2710.32")
    assert convertir(Decimal("1000.00"), "CRC", "USD", tasa) == Decimal("2.21")


def test_un_fallo_de_red_sale_como_error_del_dominio_y_no_como_httpx() -> None:
    """Una excepción de httpx cruda se escaparía de todos los `except` de la app.

    Es lo que pasó de verdad: Hacienda tardó en responder, el `ReadTimeout` se
    coló hasta arriba y tumbó una sincronización de correo entera con un 500,
    cuando el tipo de cambio en esa operación es apenas un extra.
    """

    def _timeout(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout", request=peticion)

    cliente = httpx.Client(transport=httpx.MockTransport(_timeout))
    servicio = TipoCambioService(cliente, _configuracion())

    with pytest.raises(ErrorDeProveedorExterno):
        servicio.obtener(date.today())
