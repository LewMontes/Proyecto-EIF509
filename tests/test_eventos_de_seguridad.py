"""Los eventos de seguridad y el 429, tal como salen de la API.

El manejador global (`presentation/errores.py`) es por donde pasan todos los
401, 403, 429 y 409, así que es el que deja cada evento en el registro
`gastonomo.seguridad`. Estas pruebas verifican lo que pide la rúbrica de
observabilidad: que los inicios de sesión fallidos, los accesos denegados y
los conflictos queden registrados, y **nunca** con la contraseña ni el token.

También las respuestas `429` del login: el límite de intentos lo cuenta
`LimitadorDeIntentos` (ver `test_endurecimiento.py`), pero el código, el
`Retry-After` y el Problem Details los pone este mismo manejador.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config.registros import FormatoJson

CONTRASENA = "una-clave-larga-y-secreta"
CORREO = "ana@gastonomo.cr"


def _eventos(caplog: pytest.LogCaptureFixture) -> list[dict]:
    return [json.loads(FormatoJson().format(r)) for r in caplog.records if hasattr(r, "evento")]


def _registrar(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/v1/usuarios",
        json={"nombre_completo": "Ana Mora", "correo": CORREO, "contrasena": CONTRASENA},
    )
    assert respuesta.status_code == 201


def _login(cliente: TestClient, contrasena: str):
    return cliente.post("/api/v1/auth/login", json={"correo": CORREO, "contrasena": contrasena})


# ---- quién pidió ----


def test_la_linea_de_acceso_dice_que_titular_pidio(
    cliente: TestClient, usuario, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    cliente.get("/api/v1/categorias")

    acceso = next(e for e in _eventos(caplog) if e["evento"] == "peticion_atendida")
    assert acceso["usuario_id"] == usuario.id, "el id del titular, nunca su token"


# ---- inicios de sesión ----


def test_un_login_fallido_queda_registrado_sin_la_contrasena(
    cliente_anonimo: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _registrar(cliente_anonimo)

    assert _login(cliente_anonimo, "intento-con-esta-clave").status_code == 401

    eventos = _eventos(caplog)
    fallido = next(e for e in eventos if e["evento"] == "inicio_sesion_fallido")
    assert fallido["registrador"] == "gastonomo.seguridad"
    assert fallido["nivel"] == "WARNING"
    assert fallido["ruta"] == "/api/v1/auth/login"
    assert fallido["codigo"] == "CredencialesInvalidas"
    todo = json.dumps(eventos)
    assert "intento-con-esta-clave" not in todo
    assert CONTRASENA not in todo


def test_un_login_exitoso_queda_registrado_con_el_titular_y_sin_el_token(
    cliente_anonimo: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    _registrar(cliente_anonimo)

    token = _login(cliente_anonimo, CONTRASENA).json()["access_token"]

    eventos = _eventos(caplog)
    exitoso = next(e for e in eventos if e["evento"] == "inicio_sesion_exitoso")
    assert exitoso["usuario_id"] > 0
    assert token not in json.dumps(eventos)


# ---- A07 · el límite de intentos, visto desde la API ----


def test_el_sexto_intento_fallido_responde_429_con_retry_after(
    cliente_anonimo: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    _registrar(cliente_anonimo)
    for _ in range(5):
        assert _login(cliente_anonimo, "clave-equivocada").status_code == 401

    bloqueado = _login(cliente_anonimo, "clave-equivocada")

    assert bloqueado.status_code == 429
    assert bloqueado.headers["content-type"] == "application/problem+json"
    assert bloqueado.json()["codigo"] == "DemasiadosIntentos"
    assert 0 < int(bloqueado.headers["Retry-After"]) <= 15 * 60
    assert any(e["evento"] == "inicio_sesion_bloqueado" for e in _eventos(caplog))


def test_durante_el_bloqueo_ni_la_contrasena_correcta_entra(cliente_anonimo: TestClient) -> None:
    """Si la correcta destrabara, el bloqueo no frenaría a quien sigue probando."""
    _registrar(cliente_anonimo)
    for _ in range(5):
        _login(cliente_anonimo, "clave-equivocada")

    assert _login(cliente_anonimo, CONTRASENA).status_code == 429


def test_un_correo_inexistente_tambien_se_bloquea(cliente_anonimo: TestClient) -> None:
    """Si solo se bloquearan las cuentas reales, el 429 delataría cuáles existen."""
    for _ in range(5):
        cliente_anonimo.post(
            "/api/v1/auth/login", json={"correo": "nadie@gastonomo.cr", "contrasena": "x"}
        )

    respuesta = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "nadie@gastonomo.cr", "contrasena": "x"}
    )

    assert respuesta.status_code == 429


# ---- accesos ----


def test_un_acceso_sin_token_queda_registrado(
    cliente_anonimo: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    assert cliente_anonimo.get("/api/v1/categorias").status_code == 401

    assert any(e["evento"] == "acceso_no_autenticado" for e in _eventos(caplog))


def test_un_acceso_denegado_queda_registrado_con_quien_lo_intento(
    cliente: TestClient, usuario, caplog: pytest.LogCaptureFixture
) -> None:
    """Un titular pidiendo la lista de cuentas, que es de `ADMIN`."""
    assert cliente.get("/api/v1/usuarios").status_code == 403

    denegado = next(e for e in _eventos(caplog) if e["evento"] == "acceso_denegado")
    assert denegado["usuario_id"] == usuario.id
    assert denegado["ruta"] == "/api/v1/usuarios"


# ---- conflictos ----


def test_un_conflicto_de_concurrencia_queda_registrado(
    cliente: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    categoria = cliente.post(
        "/api/v1/categorias", json={"nombre": "Supermercado", "color_hex": "#22C55E"}
    ).json()
    presupuesto = cliente.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria["id"],
            "anio": 2026,
            "mes": 10,
            "moneda": "CRC",
            "monto_limite": "100000.00",
        },
    ).json()
    ruta = f"/api/v1/presupuestos/{presupuesto['id']}"
    cliente.put(ruta, json={"monto_limite": "120000.00", "umbral_alerta": 80, "version": 1})

    segunda = cliente.put(
        ruta, json={"monto_limite": "90000.00", "umbral_alerta": 80, "version": 1}
    )

    assert segunda.status_code == 409
    conflicto = next(e for e in _eventos(caplog) if e["evento"] == "conflicto_de_concurrencia")
    assert conflicto["ruta"] == ruta
