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
    assert "/api/categorias" in respuesta.json()["paths"]
