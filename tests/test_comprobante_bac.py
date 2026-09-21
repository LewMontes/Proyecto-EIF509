"""El lector de comprobantes de BAC, probado contra una muestra real anonimizada."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.business.parsers.comprobante_bac import parsear_comprobante_bac

MUESTRAS = Path(__file__).parent / "fixtures"


@pytest.fixture
def comprobante_de_compra() -> str:
    return (MUESTRAS / "comprobante_bac_compra.txt").read_text(encoding="utf-8")


def test_lee_los_campos_de_una_compra(comprobante_de_compra: str) -> None:
    resultado = parsear_comprobante_bac(comprobante_de_compra)

    assert resultado.banco == "BAC Credomatic"
    assert resultado.comercio == "WALMART SAN SEBASTIAN"
    assert resultado.ciudad == "SAN JOSE"
    assert resultado.pais == "Costa Rica"
    assert resultado.fecha == datetime(2026, 8, 30, 13, 27)
    assert resultado.marca_tarjeta == "AMEX"
    assert resultado.ultimos_cuatro == "4321"
    assert resultado.autorizacion == "100200"
    assert resultado.referencia == "99887766"
    assert resultado.tipo_transaccion == "COMPRA"
    assert resultado.moneda == "CRC"
    assert resultado.monto == Decimal("7870.00")


def test_el_monto_es_decimal_exacto(comprobante_de_compra: str) -> None:
    """Con punto flotante el reporte no cuadra por centimos."""
    resultado = parsear_comprobante_bac(comprobante_de_compra)

    assert isinstance(resultado.monto, Decimal)
    assert resultado.monto * 3 == Decimal("23610.00")


def test_una_compra_completa_es_confiable(comprobante_de_compra: str) -> None:
    resultado = parsear_comprobante_bac(comprobante_de_compra)

    assert resultado.confianza == 1.0
    assert resultado.es_confiable is True
    assert resultado.es_compra is True


def test_tolera_los_acentos_correctos(comprobante_de_compra: str) -> None:
    """El mismo comprobante, pero leido de una fuente que si conserva los acentos."""
    con_acentos = comprobante_de_compra.replace("Autorizaci?n", "Autorización").replace(
        "Tipo de Transacci?n", "Tipo de Transacción"
    )

    resultado = parsear_comprobante_bac(con_acentos)

    assert resultado.autorizacion == "100200"
    assert resultado.tipo_transaccion == "COMPRA"


def test_una_anulacion_no_es_una_compra(comprobante_de_compra: str) -> None:
    """Las notificaciones tambien llegan por anulaciones, y esas no son gasto nuevo."""
    anulacion = comprobante_de_compra.replace(
        "Tipo de Transacci?n: COMPRA", "Tipo de Transacci?n: ANULACION"
    )

    resultado = parsear_comprobante_bac(anulacion)

    assert resultado.tipo_transaccion == "ANULACION"
    assert resultado.es_compra is False


def test_un_comprobante_incompleto_baja_la_confianza_en_vez_de_reventar() -> None:
    resultado = parsear_comprobante_bac("Comercio: TIENDA X\nMonto: CRC 1,000.00")

    assert resultado.comercio == "TIENDA X"
    assert resultado.monto == Decimal("1000.00")
    assert resultado.fecha is None
    assert resultado.ultimos_cuatro is None
    assert resultado.confianza == 0.5
    assert resultado.es_confiable is False


def test_un_texto_que_no_es_un_comprobante_no_extrae_nada() -> None:
    resultado = parsear_comprobante_bac("Buenos dias, le recordamos su cita del martes.")

    assert resultado.confianza == 0.0
    assert resultado.es_confiable is False


def test_reconoce_las_otras_marcas_de_tarjeta(comprobante_de_compra: str) -> None:
    visa = comprobante_de_compra.replace("AMEX: ***********4321", "VISA: ***********4321")

    resultado = parsear_comprobante_bac(visa)

    assert resultado.marca_tarjeta == "VISA"
    assert resultado.ultimos_cuatro == "4321"


def test_lee_montos_en_dolares(comprobante_de_compra: str) -> None:
    en_dolares = comprobante_de_compra.replace("Monto: CRC 7,870.00", "Monto: USD 15.99")

    resultado = parsear_comprobante_bac(en_dolares)

    assert resultado.moneda == "USD"
    assert resultado.monto == Decimal("15.99")
