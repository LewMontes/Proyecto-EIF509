"""Las correcciones de la auditoría de seguridad del Laboratorio 7.

Una prueba por corrección, para que ninguna se pueda deshacer sin que el CI lo
note. El hallazgo que justifica cada una está en AUDITORIA-SEGURIDAD.md.
"""

import pytest
from fastapi.testclient import TestClient

from app.business.errors import DemasiadosIntentos
from app.business.seguridad.intentos import LimitadorDeIntentos
from app.config.settings import LARGO_MINIMO_JWT, _obtener_jwt_secreto

CONTRASENA = "una-clave-larga"
CORREO = "ana@gastonomo.cr"


def _registrar(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/v1/usuarios",
        json={"nombre_completo": "Ana Mora", "correo": CORREO, "contrasena": CONTRASENA},
    )
    assert respuesta.status_code == 201


def _login(cliente: TestClient, contrasena: str):
    return cliente.post("/api/v1/auth/login", json={"correo": CORREO, "contrasena": contrasena})


# ---- A07 · fuerza bruta contra el login ----
#
# Acá, el conteo. Cómo sale el bloqueo por la API -el 429 con `Retry-After`-
# lo prueba `test_eventos_de_seguridad.py`, junto al manejador que lo produce.


def test_un_login_exitoso_borra_los_fallos_anteriores(cliente_anonimo: TestClient) -> None:
    _registrar(cliente_anonimo)
    for _ in range(4):
        _login(cliente_anonimo, "clave-equivocada")
    assert _login(cliente_anonimo, CONTRASENA).status_code == 200

    for _ in range(4):
        assert _login(cliente_anonimo, "clave-equivocada").status_code == 401


def test_cuatro_fallos_todavia_no_bloquean(cliente_anonimo: TestClient) -> None:
    _registrar(cliente_anonimo)
    for _ in range(4):
        _login(cliente_anonimo, "clave-equivocada")

    assert _login(cliente_anonimo, CONTRASENA).status_code == 200


class _Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora


def test_el_bloqueo_se_levanta_solo_al_pasar_la_ventana() -> None:
    reloj = _Reloj()
    limitador = LimitadorDeIntentos(maximo=3, ventana_en_segundos=60, reloj=reloj)
    for _ in range(3):
        limitador.registrar_fallo("ana")

    with pytest.raises(DemasiadosIntentos) as bloqueo:
        limitador.verificar("ana")
    assert bloqueo.value.segundos_de_espera == 60

    reloj.ahora += 61
    limitador.verificar("ana")  # ya no lanza


def test_el_limitador_cuenta_cada_clave_por_separado() -> None:
    limitador = LimitadorDeIntentos(maximo=2, ventana_en_segundos=60)
    limitador.registrar_fallo("ana")
    limitador.registrar_fallo("ana")

    limitador.verificar("luis")  # otra cuenta, sin bloqueo
    with pytest.raises(DemasiadosIntentos):
        limitador.verificar("ana")


# ---- A02 · configuración insegura ----


def test_toda_respuesta_lleva_las_cabeceras_de_seguridad(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get("/api/salud")

    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert respuesta.headers["Referrer-Policy"] == "no-referrer"
    assert "max-age=" in respuesta.headers["Strict-Transport-Security"]
    assert respuesta.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert respuesta.headers["Cache-Control"] == "no-store"


def test_los_errores_tambien_llevan_las_cabeceras(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get("/api/v1/categorias")

    assert respuesta.status_code == 401
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"


def test_swagger_ui_sigue_funcionando_sin_la_politica_estricta(
    cliente_anonimo: TestClient,
) -> None:
    respuesta = cliente_anonimo.get("/docs")

    assert respuesta.status_code == 200
    assert "Content-Security-Policy" not in respuesta.headers


def test_cors_solo_responde_a_los_origenes_configurados(cliente_anonimo: TestClient) -> None:
    preflight = {"Access-Control-Request-Method": "GET"}

    permitido = cliente_anonimo.options(
        "/api/v1/categorias", headers={"Origin": "http://localhost:5173", **preflight}
    )
    ajeno = cliente_anonimo.options(
        "/api/v1/categorias", headers={"Origin": "https://sitio-malicioso.example", **preflight}
    )

    assert permitido.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in ajeno.headers
    assert "access-control-allow-credentials" not in permitido.headers, "la API no usa cookies"


# ---- A04 · secretos: en producción no se arranca sin una clave fuerte ----


def test_en_produccion_sin_clave_jwt_la_app_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GASTONOMO_JWT_SECRETO", raising=False)

    with pytest.raises(RuntimeError, match="GASTONOMO_JWT_SECRETO"):
        _obtener_jwt_secreto("produccion")


def test_en_produccion_una_clave_jwt_corta_tampoco_sirve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GASTONOMO_JWT_SECRETO", "corta")

    with pytest.raises(RuntimeError):
        _obtener_jwt_secreto("produccion")


def test_en_produccion_una_clave_jwt_larga_se_acepta(monkeypatch: pytest.MonkeyPatch) -> None:
    clave = "x" * LARGO_MINIMO_JWT
    monkeypatch.setenv("GASTONOMO_JWT_SECRETO", clave)

    assert _obtener_jwt_secreto("produccion") == clave
