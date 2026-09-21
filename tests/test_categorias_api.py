"""La API de categorias, incluida la traduccion de errores de negocio a HTTP."""

from fastapi.testclient import TestClient

from app.data.models.usuario import Usuario


def test_crear_categoria_devuelve_201_con_la_categoria(
    cliente: TestClient, usuario: Usuario
) -> None:
    respuesta = cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Alimentacion", "color_hex": "#2563EB"},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Alimentacion"
    assert cuerpo["usuario_id"] == usuario.id
    assert cuerpo["es_hoja"] is True


def test_nombre_repetido_se_traduce_a_409(cliente: TestClient, usuario: Usuario) -> None:
    peticion = {"usuario_id": usuario.id, "nombre": "Alimentacion", "color_hex": "#2563EB"}
    cliente.post("/api/categorias", json=peticion)

    respuesta = cliente.post("/api/categorias", json=peticion)

    assert respuesta.status_code == 409
    assert "Ya existe" in respuesta.json()["detalle"]


def test_color_invalido_se_traduce_a_422(cliente: TestClient, usuario: Usuario) -> None:
    respuesta = cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Transporte", "color_hex": "#ZZZZZZ"},
    )

    assert respuesta.status_code == 422
    assert "hexadecimal" in respuesta.json()["detalle"]


def test_usuario_id_mas_alla_de_lo_que_soporta_la_columna_da_422(cliente: TestClient) -> None:
    """Regresión: un id absurdamente grande pasa la validación de FastAPI (es un
    int válido) y solo revienta al convertirlo al INTEGER real de la columna.
    Sin un manejador para sqlalchemy.exc.DataError, esto se colaba como un
    500 crudo en vez de un 422 con mensaje -no es un caso solo de PostgreSQL,
    también se ve sobre SQLite (motor de estas pruebas).
    """
    respuesta = cliente.get("/api/categorias", params={"usuario_id": 99999999999999999999999999})

    assert respuesta.status_code == 422


def test_listar_categorias_de_un_usuario(cliente: TestClient, usuario: Usuario) -> None:
    cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Alimentacion", "color_hex": "#2563EB"},
    )
    cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Transporte", "color_hex": "#16A34A"},
    )

    respuesta = cliente.get("/api/categorias", params={"usuario_id": usuario.id})

    assert respuesta.status_code == 200
    assert [categoria["nombre"] for categoria in respuesta.json()] == [
        "Alimentacion",
        "Transporte",
    ]


def test_listar_sin_usuario_id_es_error_de_validacion(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/categorias")

    assert respuesta.status_code == 422
