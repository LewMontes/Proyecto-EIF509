"""Observabilidad mínima: el health check y los registros estructurados.

Lo que se verifica es lo que pide el laboratorio:

- `/actuator/health` expuesto, público y **sin detalles**.
- Registros estructurados: una línea JSON por evento, con `id_peticion`, y
  nada sensible en ellos.

Los eventos de seguridad que el manejador global escribe sobre estos mismos
registros se prueban en `test_eventos_de_seguridad.py`.
"""

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.database import obtener_sesion
from app.config.registros import REDACTADO, FormatoJson

CONTRASENA = "una-clave-larga-y-secreta"


def _como_json(registro: logging.LogRecord) -> dict:
    """La línea que ese registro escribiría en stdout, ya leída como JSON."""
    return json.loads(FormatoJson().format(registro))


def _eventos(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [_como_json(r) for r in caplog.records if hasattr(r, "evento")]


# ---- /actuator/health ----


def test_el_health_check_es_publico_y_dice_up(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get("/actuator/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "UP"}, "sin detalles: ni base, ni versión, ni disco"


class _SesionCaida:
    def execute(self, *_args, **_kwargs):
        raise ConnectionError("could not connect to server: Connection refused")


def test_sin_base_de_datos_el_health_check_dice_down_con_503(
    aplicacion: FastAPI, cliente_anonimo: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    aplicacion.dependency_overrides[obtener_sesion] = lambda: _SesionCaida()

    respuesta = cliente_anonimo.get("/actuator/health")

    assert respuesta.status_code == 503
    assert respuesta.json() == {"status": "DOWN"}
    assert "Connection refused" not in respuesta.text, "el porqué queda en el registro"
    assert any(e.get("evento") == "salud_caida" for e in _eventos(caplog))


# ---- registros estructurados ----


def test_cada_registro_sale_como_una_linea_json_con_campos_fijos() -> None:
    registro = logging.LogRecord(
        "gastonomo.prueba", logging.WARNING, __file__, 1, "Algo pasó en %s", ("compras",), None
    )
    registro.evento = "algo_paso"

    linea = FormatoJson().format(registro)

    assert "\n" not in linea, "una sola línea por evento"
    cuerpo = json.loads(linea)
    assert cuerpo["nivel"] == "WARNING"
    assert cuerpo["registrador"] == "gastonomo.prueba"
    assert cuerpo["mensaje"] == "Algo pasó en compras"
    assert cuerpo["evento"] == "algo_paso"
    assert cuerpo["momento"].endswith("+00:00"), "en UTC"


def test_un_campo_con_nombre_de_secreto_se_redacta() -> None:
    registro = logging.LogRecord("gastonomo", logging.INFO, __file__, 1, "x", None, None)
    registro.contrasena = CONTRASENA
    registro.authorization = "Bearer eyJhbGciOi..."
    registro.access_token = "eyJhbGciOi..."

    cuerpo = _como_json(registro)

    assert cuerpo["contrasena"] == cuerpo["authorization"] == cuerpo["access_token"] == REDACTADO
    assert CONTRASENA not in json.dumps(cuerpo)


def test_cada_peticion_deja_una_linea_de_acceso_sin_query_string(
    cliente: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    respuesta = cliente.get("/api/v1/categorias", params={"token": "no-deberia-verse"})

    acceso = next(e for e in _eventos(caplog) if e["evento"] == "peticion_atendida")
    assert acceso["ruta"] == "/api/v1/categorias"
    assert acceso["metodo"] == "GET"
    assert acceso["estado"] == respuesta.status_code
    assert acceso["duracion_ms"] >= 0
    assert acceso["id_peticion"] == respuesta.headers["X-Request-ID"]
    assert "no-deberia-verse" not in json.dumps(acceso)
    assert "Bearer" not in json.dumps(acceso)


def test_el_id_de_peticion_del_cliente_se_respeta_si_es_seguro(
    cliente_anonimo: TestClient,
) -> None:
    propio = cliente_anonimo.get("/api/salud", headers={"X-Request-ID": "abc-123"})
    raro = cliente_anonimo.get("/api/salud", headers={"X-Request-ID": "a b <script>"})

    assert propio.headers["X-Request-ID"] == "abc-123"
    assert raro.headers["X-Request-ID"] != "a b <script>", "no se copia al registro tal cual"
