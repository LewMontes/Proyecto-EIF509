"""Prueba del recorrido completo: HTTP -> presentacion -> negocio -> datos."""


def test_crear_y_listar_categorias(cliente, usuario):
    creacion = cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Alimentacion", "color_hex": "#16A34A"},
    )
    assert creacion.status_code == 201
    assert creacion.json()["nombre"] == "Alimentacion"

    listado = cliente.get("/api/categorias", params={"usuario_id": usuario.id})
    assert listado.status_code == 200
    assert [c["nombre"] for c in listado.json()] == ["Alimentacion"]


def test_el_nombre_repetido_devuelve_409(cliente, usuario):
    """Comprueba que el error de negocio se traduce al codigo HTTP correcto."""
    payload = {"usuario_id": usuario.id, "nombre": "Transporte"}
    cliente.post("/api/categorias", json=payload)

    repetida = cliente.post("/api/categorias", json=payload)

    assert repetida.status_code == 409
    assert "Ya existe" in repetida.json()["detalle"]


def test_el_color_invalido_devuelve_422(cliente, usuario):
    respuesta = cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Ocio", "color_hex": "#ZZZZZZ"},
    )

    assert respuesta.status_code == 422
