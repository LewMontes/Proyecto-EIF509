"""El Proceso 2 desde la API: `POST /api/v1/comprobantes`.

Hasta el Laboratorio 4, `ConciliacionService.conciliar` solo se ejecutaba desde
las pruebas. Estas son las que fijan que ahora está conectado: mandar un
comprobante por la API termina en una compra real, con su presupuesto
impactado y el comprobante ligado.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.business.services.tipo_cambio_service import TipoDeCambio
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.presentation.dependencies import obtener_servicio_de_tipo_cambio
from tests.conftest import cabecera_de


@pytest.fixture
def buzon(cliente: TestClient) -> int:
    respuesta = cliente.post(
        "/api/v1/cuentas-correo", json={"proveedor": "GMAIL", "direccion": "Ana@Gmail.com"}
    )
    assert respuesta.status_code == 201
    assert respuesta.headers["Location"] == f"/api/v1/cuentas-correo/{respuesta.json()['id']}"
    return respuesta.json()["id"]


def _comprobante(buzon: int, **extra) -> dict:
    return {
        "cuenta_correo_id": buzon,
        "mensaje_id": "AAMk-0001",
        "remitente": "notificacion@baccredomatic.cr",
        "banco": "BAC Credomatic",
        "comercio": "WALMART SAN SEBASTIAN",
        "monto": "7870.00",
        "moneda": "CRC",
        "fecha": "2026-08-30T13:27:00",
        "ultimos_cuatro": "4321",
        **extra,
    }


# ---- el buzón ----


def test_el_buzon_se_guarda_en_minusculas_y_sin_tokens(cliente: TestClient, buzon: int) -> None:
    cuerpo = cliente.get(f"/api/v1/cuentas-correo/{buzon}").json()

    assert cuerpo["direccion"] == "ana@gmail.com"
    assert cuerpo["estado"] == "ACTIVA"
    assert set(cuerpo) == {"id", "proveedor", "direccion", "estado", "ultima_sincronizacion"}
    assert [c["id"] for c in cliente.get("/api/v1/cuentas-correo").json()] == [buzon]


def test_registrar_dos_veces_el_mismo_buzon_da_409(cliente: TestClient, buzon: int) -> None:
    respuesta = cliente.post(
        "/api/v1/cuentas-correo", json={"proveedor": "GMAIL", "direccion": "ana@gmail.com"}
    )

    assert respuesta.status_code == 409


# ---- el proceso completo ----


def test_un_comprobante_completo_termina_en_una_compra_con_su_presupuesto(
    cliente: TestClient, buzon: int
) -> None:
    """Las cinco tablas, por la API: comprobante, compra, renglón, regla y presupuesto."""
    categoria = cliente.post(
        "/api/v1/categorias", json={"nombre": "Supermercado", "color_hex": "#2563EB"}
    ).json()
    cliente.post(
        "/api/v1/metodos-pago",
        json={"alias": "Visa BAC", "tipo": "CREDITO", "ultimos_cuatro": "4321"},
    )
    regla = cliente.post(
        "/api/v1/reglas-categorizacion",
        json={"nombre": "Walmart", "patron": "WALMART", "categoria_destino_id": categoria["id"]},
    ).json()
    presupuesto = cliente.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria["id"],
            "anio": 2026,
            "mes": 8,
            "moneda": "CRC",
            "monto_limite": "9000.00",
        },
    ).json()

    respuesta = cliente.post("/api/v1/comprobantes", json=_comprobante(buzon))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert respuesta.headers["Location"] == f"/api/v1/comprobantes/{cuerpo['id']}"
    assert cuerpo["estado"] == "PROCESADO"
    assert cuerpo["compra_id"] is not None
    assert cuerpo["confianza"] == 1.0

    compra = cliente.get(f"/api/v1/compras/{cuerpo['compra_id']}").json()
    assert compra["origen"] == "INGESTA_CORREO"
    assert compra["comercio_nombre"] == "WALMART SAN SEBASTIAN"
    assert compra["metodo_pago_alias"] == "Visa BAC"
    assert compra["categoria_nombre"] == "Supermercado"
    assert compra["requiere_revision"] is False
    assert Decimal(compra["total"]) == Decimal("7870.00")

    consumido = cliente.get(f"/api/v1/presupuestos/{presupuesto['id']}").json()["monto_consumido"]
    assert Decimal(consumido) == Decimal("7870.00")
    veces = cliente.get(f"/api/v1/reglas-categorizacion/{regla['id']}").json()["veces_aplicada"]
    assert veces == 1


def test_sin_tarjeta_ni_categoria_la_compra_se_crea_marcada_para_revision(
    cliente: TestClient, buzon: int
) -> None:
    cuerpo = cliente.post("/api/v1/comprobantes", json=_comprobante(buzon)).json()

    assert cuerpo["estado"] == "PROCESADO"
    compra = cliente.get(f"/api/v1/compras/{cuerpo['compra_id']}").json()
    assert compra["requiere_revision"] is True
    assert compra["metodo_pago_id"] is None
    assert compra["categoria_id"] is None
    revision = cliente.get("/api/v1/compras", params={"requiere_revision": True}).json()[
        "contenido"
    ]
    assert [c["id"] for c in revision] == [compra["id"]]


def test_el_mismo_mensaje_no_se_recibe_dos_veces(cliente: TestClient, buzon: int) -> None:
    """La ingesta es idempotente: reentregar el correo no duplica el gasto."""
    assert cliente.post("/api/v1/comprobantes", json=_comprobante(buzon)).status_code == 201

    repetido = cliente.post("/api/v1/comprobantes", json=_comprobante(buzon))

    assert repetido.status_code == 409
    assert len(cliente.get("/api/v1/compras").json()["contenido"]) == 1
    assert len(cliente.get("/api/v1/comprobantes").json()["contenido"]) == 1


def test_con_poca_confianza_queda_en_revision_manual_y_no_crea_compra(
    cliente: TestClient, buzon: int
) -> None:
    """Sin comercio ni tarjeta solo hay 2 de 4 campos: 0.50 de confianza."""
    cuerpo = _comprobante(buzon)
    del cuerpo["comercio"], cuerpo["ultimos_cuatro"]

    respuesta = cliente.post("/api/v1/comprobantes", json=cuerpo)

    assert respuesta.status_code == 201, "el comprobante sí se recibió"
    assert respuesta.json()["estado"] == "REVISION_MANUAL"
    assert respuesta.json()["confianza"] == 0.5
    assert respuesta.json()["compra_id"] is None
    assert respuesta.json()["motivo_fallo"]
    assert cliente.get("/api/v1/compras").json()["contenido"] == []
    # Y uno en revisión manual no se reintenta: lo resuelve una persona.
    ruta = f"/api/v1/comprobantes/{respuesta.json()['id']}/reintentos"
    assert cliente.post(ruta).status_code == 409


# ---- tipo de cambio ----


def test_en_dolares_sin_tipo_de_cambio_queda_pendiente_y_se_concilia_al_reintentar(
    aplicacion: FastAPI, cliente: TestClient, buzon: int
) -> None:
    """«Queda pendiente hasta que la tasa exista. No se inventa una tasa aproximada.»"""
    respuesta = cliente.post(
        "/api/v1/comprobantes", json=_comprobante(buzon, moneda="USD", monto="10.00")
    )

    assert respuesta.status_code == 201
    pendiente = respuesta.json()
    assert pendiente["estado"] == "PARSEADO"
    assert pendiente["compra_id"] is None
    assert "tipo de cambio" in pendiente["motivo_fallo"]
    assert pendiente["intentos_procesamiento"] == 0
    assert cliente.get("/api/v1/compras").json()["contenido"] == []
    pendientes = cliente.get("/api/v1/comprobantes", params={"estado": "PARSEADO"}).json()[
        "contenido"
    ]
    assert [c["id"] for c in pendientes] == [pendiente["id"]]

    class _TasaFija:
        def obtener(self, fecha: date | None = None) -> TipoDeCambio:
            return TipoDeCambio(fecha=fecha, compra=Decimal("545"), venta=Decimal("550"))

    aplicacion.dependency_overrides[obtener_servicio_de_tipo_cambio] = _TasaFija
    reintento = cliente.post(f"/api/v1/comprobantes/{pendiente['id']}/reintentos")

    assert reintento.status_code == 200
    assert reintento.json()["estado"] == "PROCESADO"
    compra = cliente.get(f"/api/v1/compras/{reintento.json()['compra_id']}").json()
    assert Decimal(compra["total_moneda_base"]) == Decimal("5500.00")
    # Ya procesado, no admite otro intento.
    assert cliente.post(f"/api/v1/comprobantes/{pendiente['id']}/reintentos").status_code == 409


# ---- tres intentos ----


def test_al_tercer_fallo_el_comprobante_queda_fallido(
    aplicacion: FastAPI, buzon: int, usuario
) -> None:
    """Un fallo inesperado responde 500 sin traza, y cuenta un intento; al tercero, FALLIDO."""
    cliente = TestClient(aplicacion, headers=cabecera_de(usuario), raise_server_exceptions=False)

    with patch.object(LineaCompraRepository, "agregar", side_effect=RuntimeError("se cayó")):
        primero = cliente.post("/api/v1/comprobantes", json=_comprobante(buzon))
        assert primero.status_code == 500
        assert "Traceback" not in primero.text and "RuntimeError" not in primero.text

        comprobante = cliente.get("/api/v1/comprobantes").json()["contenido"][0]
        assert comprobante["estado"] == "PARSEADO"
        assert comprobante["intentos_procesamiento"] == 1
        ruta = f"/api/v1/comprobantes/{comprobante['id']}/reintentos"

        assert cliente.post(ruta).status_code == 500
        assert cliente.post(ruta).status_code == 500

    fallido = cliente.get(f"/api/v1/comprobantes/{comprobante['id']}").json()
    assert fallido["estado"] == "FALLIDO"
    assert fallido["intentos_procesamiento"] == 3
    assert "se cayó" in fallido["motivo_fallo"]
    assert cliente.post(ruta).status_code == 409, "no hay un cuarto intento"
    assert cliente.get("/api/v1/compras").json()["contenido"] == []


# ---- validación del DTO de entrada ----


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("monto", "0"),
        ("monto", "-50.00"),
        ("moneda", "XYZ"),
        ("fecha", (datetime.now() + timedelta(days=1)).isoformat()),
        ("ultimos_cuatro", "12"),
        ("confianza", 1.5),
    ],
)
def test_el_dto_rechaza_la_forma_antes_de_llegar_al_negocio(
    cliente: TestClient, buzon: int, campo: str, valor
) -> None:
    """Monto positivo, fecha no futura y moneda reconocida: lo valida Pydantic.

    Es forma, no regla de negocio: `400` con el campo que falló, no `422`.
    """
    respuesta = cliente.post("/api/v1/comprobantes", json=_comprobante(buzon, **{campo: valor}))

    assert respuesta.status_code == 400
    assert respuesta.headers["content-type"] == "application/problem+json"
    assert [error["campo"] for error in respuesta.json()["errores"]] == [f"body.{campo}"]
    assert cliente.get("/api/v1/comprobantes").json()["contenido"] == [], "no se guardó nada"


# ---- propiedad ----


def test_no_se_manda_un_comprobante_al_buzon_de_otro_titular(
    aplicacion: FastAPI, buzon: int, otro_usuario
) -> None:
    intruso = TestClient(aplicacion, headers=cabecera_de(otro_usuario))

    assert intruso.post("/api/v1/comprobantes", json=_comprobante(buzon)).status_code == 404
    assert intruso.get(f"/api/v1/cuentas-correo/{buzon}").status_code == 404


def test_el_comprobante_de_otro_titular_no_se_ve_ni_se_reintenta(
    aplicacion: FastAPI, cliente: TestClient, buzon: int, otro_usuario
) -> None:
    comprobante_id = cliente.post("/api/v1/comprobantes", json=_comprobante(buzon)).json()["id"]
    intruso = TestClient(aplicacion, headers=cabecera_de(otro_usuario))

    assert intruso.get(f"/api/v1/comprobantes/{comprobante_id}").status_code == 404
    assert intruso.post(f"/api/v1/comprobantes/{comprobante_id}/reintentos").status_code == 404
    assert intruso.get("/api/v1/comprobantes").json()["contenido"] == []
