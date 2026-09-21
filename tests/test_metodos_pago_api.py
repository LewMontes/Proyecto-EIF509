"""La API de métodos de pago, de punta a punta contra la base de prueba."""

from fastapi.testclient import TestClient

from app.data.models.usuario import Usuario


def test_crear_y_listar_metodo_de_pago(cliente: TestClient, usuario: Usuario) -> None:
    creacion = cliente.post(
        "/api/metodos-pago",
        json={
            "usuario_id": usuario.id,
            "alias": "Visa BAC",
            "tipo": "CREDITO",
            "moneda": "CRC",
            "ultimos_cuatro": "4321",
            "entidad": "BAC",
            "dia_corte": 15,
        },
    )
    assert creacion.status_code == 200
    cuerpo = creacion.json()
    assert cuerpo["alias"] == "Visa BAC"
    assert cuerpo["activo"] is True

    listado = cliente.get("/api/metodos-pago", params={"usuario_id": usuario.id})
    assert listado.status_code == 200
    assert len(listado.json()) == 1


def test_crear_efectivo_sin_ultimos_cuatro(cliente: TestClient, usuario: Usuario) -> None:
    respuesta = cliente.post(
        "/api/metodos-pago",
        json={"usuario_id": usuario.id, "alias": "Efectivo", "tipo": "EFECTIVO"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["ultimos_cuatro"] is None


def test_rechaza_ultimos_cuatro_en_efectivo(cliente: TestClient, usuario: Usuario) -> None:
    respuesta = cliente.post(
        "/api/metodos-pago",
        json={
            "usuario_id": usuario.id,
            "alias": "Efectivo",
            "tipo": "EFECTIVO",
            "ultimos_cuatro": "0000",
        },
    )

    assert respuesta.status_code == 409


def test_desactivar_metodo_de_pago(cliente: TestClient, usuario: Usuario) -> None:
    creado = cliente.post(
        "/api/metodos-pago",
        json={"usuario_id": usuario.id, "alias": "Efectivo", "tipo": "EFECTIVO"},
    ).json()

    respuesta = cliente.delete(
        f"/api/metodos-pago/{creado['id']}", params={"usuario_id": usuario.id}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False
