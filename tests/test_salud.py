"""La aplicacion levanta y responde. Es lo que verifica la CI en cada push."""

from fastapi.testclient import TestClient

from app.main import crear_app

cliente_simple = TestClient(crear_app())


def test_endpoint_de_salud_responde_ok():
    respuesta = cliente_simple.get("/api/salud")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "OK - sistema en linea"


def test_la_documentacion_openapi_se_genera():
    """Si el esquema se genera, todos los routers y DTOs son coherentes entre si."""
    respuesta = cliente_simple.get("/openapi.json")

    assert respuesta.status_code == 200
    rutas = respuesta.json()["paths"]
    assert "/api/v1/categorias" in rutas
    assert "/api/v1/auth/login" in rutas
    assert "/api/v1/compras" in rutas, "el Proceso 1"
    assert "/api/v1/comprobantes" in rutas, "el Proceso 2"


def test_todo_el_contrato_de_negocio_vive_bajo_la_version():
    """Salvo el endpoint de salud, ninguna ruta queda fuera de `/api/v1`."""
    rutas = cliente_simple.get("/openapi.json").json()["paths"]

    assert [ruta for ruta in rutas if not ruta.startswith("/api/v1/")] == ["/api/salud"]
