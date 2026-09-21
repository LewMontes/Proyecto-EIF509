"""La API de reglas de categorización, de punta a punta contra la base de prueba."""

from fastapi.testclient import TestClient

from app.data.models.usuario import Usuario


def _crear_categoria(cliente: TestClient, usuario: Usuario, nombre: str = "Supermercado") -> int:
    respuesta = cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": nombre, "color_hex": "#22C55E"},
    )
    assert respuesta.status_code == 201
    return respuesta.json()["id"]


def test_crear_y_listar_regla(cliente: TestClient, usuario: Usuario) -> None:
    categoria_id = _crear_categoria(cliente, usuario)

    creacion = cliente.post(
        "/api/reglas-categorizacion",
        json={
            "usuario_id": usuario.id,
            "nombre": "Walmart es supermercado",
            "patron": "WALMART",
            "categoria_destino_id": categoria_id,
        },
    )

    assert creacion.status_code == 200
    cuerpo = creacion.json()
    assert cuerpo["nombre"] == "Walmart es supermercado"
    assert cuerpo["categoria_destino_nombre"] == "Supermercado"
    assert cuerpo["prioridad"] == 1
    assert cuerpo["activa"] is True
    assert cuerpo["veces_aplicada"] == 0

    listado = cliente.get("/api/reglas-categorizacion", params={"usuario_id": usuario.id})
    assert listado.status_code == 200
    assert len(listado.json()) == 1


def test_rechaza_prioridad_repetida(cliente: TestClient, usuario: Usuario) -> None:
    categoria_id = _crear_categoria(cliente, usuario)
    cliente.post(
        "/api/reglas-categorizacion",
        json={
            "usuario_id": usuario.id,
            "nombre": "Regla A",
            "patron": "WALMART",
            "categoria_destino_id": categoria_id,
            "prioridad": 3,
        },
    )

    respuesta = cliente.post(
        "/api/reglas-categorizacion",
        json={
            "usuario_id": usuario.id,
            "nombre": "Regla B",
            "patron": "MAXIPALI",
            "categoria_destino_id": categoria_id,
            "prioridad": 3,
        },
    )

    assert respuesta.status_code == 409


def test_desactivar_regla(cliente: TestClient, usuario: Usuario) -> None:
    categoria_id = _crear_categoria(cliente, usuario)
    creada = cliente.post(
        "/api/reglas-categorizacion",
        json={
            "usuario_id": usuario.id,
            "nombre": "Regla",
            "patron": "WALMART",
            "categoria_destino_id": categoria_id,
        },
    ).json()

    respuesta = cliente.delete(
        f"/api/reglas-categorizacion/{creada['id']}", params={"usuario_id": usuario.id}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["activa"] is False
