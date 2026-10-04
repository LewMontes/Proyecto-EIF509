"""El contrato REST de las entidades principales: verbos, rutas y códigos.

Las reglas de cada servicio se prueban en su propio archivo; acá solo lo que
agrega la capa de presentación -que crear responda `201` con `Location`, que
desactivar responda `204`, que lo que no existe sea `404` y lo que choca `409`.
"""

from fastapi.testclient import TestClient


def _categoria(cliente: TestClient, nombre: str = "Supermercado", **extra) -> dict:
    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": nombre, "color_hex": "#22C55E", **extra}
    )
    assert respuesta.status_code == 201
    return respuesta.json()


# ---- categorías ----


def test_crear_categoria_devuelve_201_con_location(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": "Alimentacion", "color_hex": "#2563EB"}
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Alimentacion"
    assert cuerpo["es_hoja"] is True
    assert respuesta.headers["Location"] == f"/api/v1/categorias/{cuerpo['id']}"
    # El `Location` apunta a un recurso que de verdad se puede consultar.
    assert cliente.get(respuesta.headers["Location"]).json() == cuerpo


def test_nombre_repetido_se_traduce_a_409(cliente: TestClient) -> None:
    _categoria(cliente, "Alimentacion")

    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": "Alimentacion", "color_hex": "#2563EB"}
    )

    assert respuesta.status_code == 409
    assert "Ya existe" in respuesta.json()["detalle"]


def test_color_invalido_se_traduce_a_422(cliente: TestClient) -> None:
    """La forma es correcta -siete caracteres- pero no cumple la regla del dominio."""
    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": "Transporte", "color_hex": "#ZZZZZZ"}
    )

    assert respuesta.status_code == 422
    assert "hexadecimal" in respuesta.json()["detalle"]


def test_listar_categorias_del_titular(cliente: TestClient) -> None:
    _categoria(cliente, "Alimentacion")
    _categoria(cliente, "Transporte")

    respuesta = cliente.get("/api/v1/categorias")

    assert respuesta.status_code == 200
    assert [categoria["nombre"] for categoria in respuesta.json()] == ["Alimentacion", "Transporte"]


def test_una_categoria_que_no_existe_da_404(cliente: TestClient) -> None:
    assert cliente.get("/api/v1/categorias/999999").status_code == 404


def test_actualizar_una_categoria_con_put(cliente: TestClient) -> None:
    categoria = _categoria(cliente, "Super")

    respuesta = cliente.put(
        f"/api/v1/categorias/{categoria['id']}",
        json={"nombre": "Supermercado", "color_hex": "#16a34a", "descripcion": "Abarrotes"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Supermercado"
    assert respuesta.json()["color_hex"] == "#16A34A"
    assert respuesta.json()["descripcion"] == "Abarrotes"


def test_renombrar_al_nombre_de_otra_categoria_da_409(cliente: TestClient) -> None:
    _categoria(cliente, "Transporte")
    categoria = _categoria(cliente, "Super")

    respuesta = cliente.put(
        f"/api/v1/categorias/{categoria['id']}",
        json={"nombre": "Transporte", "color_hex": "#111111"},
    )

    assert respuesta.status_code == 409


def test_desactivar_una_categoria_da_204_y_deja_de_listarse(cliente: TestClient) -> None:
    categoria = _categoria(cliente)

    respuesta = cliente.delete(f"/api/v1/categorias/{categoria['id']}")

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert cliente.get("/api/v1/categorias").json() == []
    # Borrado lógico: sigue consultable por su id, ya inactiva.
    assert cliente.get(f"/api/v1/categorias/{categoria['id']}").json()["activa"] is False


def test_no_se_desactiva_una_categoria_con_subcategorias_activas(cliente: TestClient) -> None:
    padre = _categoria(cliente, "Alimentacion")
    hija = _categoria(cliente, "Supermercado", categoria_padre_id=padre["id"])

    assert cliente.delete(f"/api/v1/categorias/{padre['id']}").status_code == 409

    # Desactivada la única hija, el padre vuelve a ser hoja y ya se puede desactivar.
    assert cliente.delete(f"/api/v1/categorias/{hija['id']}").status_code == 204
    assert cliente.get(f"/api/v1/categorias/{padre['id']}").json()["es_hoja"] is True
    assert cliente.delete(f"/api/v1/categorias/{padre['id']}").status_code == 204


# ---- métodos de pago ----


def test_crear_consultar_y_listar_metodo_de_pago(cliente: TestClient) -> None:
    creacion = cliente.post(
        "/api/v1/metodos-pago",
        json={
            "alias": "Visa BAC",
            "tipo": "CREDITO",
            "moneda": "CRC",
            "ultimos_cuatro": "4321",
            "entidad": "BAC",
            "dia_corte": 15,
        },
    )

    assert creacion.status_code == 201
    cuerpo = creacion.json()
    assert creacion.headers["Location"] == f"/api/v1/metodos-pago/{cuerpo['id']}"
    assert cliente.get(creacion.headers["Location"]).json() == cuerpo
    assert len(cliente.get("/api/v1/metodos-pago").json()) == 1


def test_rechaza_ultimos_cuatro_en_efectivo(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/v1/metodos-pago",
        json={"alias": "Efectivo", "tipo": "EFECTIVO", "ultimos_cuatro": "0000"},
    )

    assert respuesta.status_code == 409


def test_desactivar_metodo_de_pago_da_204(cliente: TestClient) -> None:
    creado = cliente.post(
        "/api/v1/metodos-pago", json={"alias": "Efectivo", "tipo": "EFECTIVO"}
    ).json()

    respuesta = cliente.delete(f"/api/v1/metodos-pago/{creado['id']}")

    assert respuesta.status_code == 204
    assert cliente.get(f"/api/v1/metodos-pago/{creado['id']}").json()["activo"] is False
    assert cliente.delete("/api/v1/metodos-pago/999999").status_code == 404


# ---- reglas de categorización ----


def _regla(cliente: TestClient, categoria_id: int, **extra) -> dict:
    cuerpo = {"nombre": "Walmart", "patron": "WALMART", "categoria_destino_id": categoria_id}
    return cliente.post("/api/v1/reglas-categorizacion", json={**cuerpo, **extra})


def test_crear_y_listar_regla(cliente: TestClient) -> None:
    categoria = _categoria(cliente)

    creacion = _regla(cliente, categoria["id"])

    assert creacion.status_code == 201
    cuerpo = creacion.json()
    assert creacion.headers["Location"] == f"/api/v1/reglas-categorizacion/{cuerpo['id']}"
    assert cuerpo["categoria_destino_nombre"] == "Supermercado"
    assert cuerpo["prioridad"] == 1
    assert cuerpo["veces_aplicada"] == 0
    assert len(cliente.get("/api/v1/reglas-categorizacion").json()) == 1


def test_rechaza_prioridad_repetida(cliente: TestClient) -> None:
    categoria = _categoria(cliente)
    _regla(cliente, categoria["id"], nombre="Regla A", prioridad=3)

    respuesta = _regla(cliente, categoria["id"], nombre="Regla B", patron="MAXIPALI", prioridad=3)

    assert respuesta.status_code == 409


def test_una_regla_hacia_una_categoria_ajena_o_inexistente_da_404(cliente: TestClient) -> None:
    assert _regla(cliente, 999999).status_code == 404


def test_desactivar_regla_da_204(cliente: TestClient) -> None:
    categoria = _categoria(cliente)
    creada = _regla(cliente, categoria["id"]).json()

    respuesta = cliente.delete(f"/api/v1/reglas-categorizacion/{creada['id']}")

    assert respuesta.status_code == 204
    assert cliente.get(f"/api/v1/reglas-categorizacion/{creada['id']}").json()["activa"] is False


# ---- presupuestos ----


def _presupuesto(cliente: TestClient, categoria_id: int):
    return cliente.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria_id,
            "anio": 2026,
            "mes": 9,
            "moneda": "CRC",
            "monto_limite": "150000.00",
        },
    )


def test_crear_y_consultar_presupuesto(cliente: TestClient) -> None:
    categoria = _categoria(cliente)

    creacion = _presupuesto(cliente, categoria["id"])

    assert creacion.status_code == 201
    cuerpo = creacion.json()
    assert creacion.headers["Location"] == f"/api/v1/presupuestos/{cuerpo['id']}"
    assert cuerpo["umbral_alerta"] == 80
    assert cuerpo["monto_consumido"] == "0.00" or float(cuerpo["monto_consumido"]) == 0
    listado = cliente.get("/api/v1/presupuestos", params={"anio": 2026, "mes": 9})
    assert [p["id"] for p in listado.json()] == [cuerpo["id"]]


def test_un_segundo_presupuesto_del_mismo_periodo_da_409(cliente: TestClient) -> None:
    categoria = _categoria(cliente)
    _presupuesto(cliente, categoria["id"])

    assert _presupuesto(cliente, categoria["id"]).status_code == 409


def test_actualizar_y_eliminar_presupuesto(cliente: TestClient) -> None:
    categoria = _categoria(cliente)
    presupuesto = _presupuesto(cliente, categoria["id"]).json()
    ruta = f"/api/v1/presupuestos/{presupuesto['id']}"

    actualizado = cliente.put(ruta, json={"monto_limite": "200000.00", "umbral_alerta": 90})

    assert actualizado.status_code == 200
    assert float(actualizado.json()["monto_limite"]) == 200000
    assert actualizado.json()["umbral_alerta"] == 90

    assert cliente.delete(ruta).status_code == 204
    assert cliente.get(ruta).status_code == 404
    assert cliente.delete(ruta).status_code == 404


# ---- comercios ----


def test_un_administrador_da_de_alta_un_comercio_y_cualquiera_lo_consulta(
    cliente_admin: TestClient, cliente: TestClient
) -> None:
    creacion = cliente_admin.post(
        "/api/v1/comercios", json={"nombre": "Walmart San Sebastián", "provincia": "San José"}
    )

    assert creacion.status_code == 201
    cuerpo = creacion.json()
    assert creacion.headers["Location"] == f"/api/v1/comercios/{cuerpo['id']}"
    assert cuerpo["nombre_normalizado"] == "WALMART SAN SEBASTIAN"
    assert cliente.get(f"/api/v1/comercios/{cuerpo['id']}").json() == cuerpo
    assert cliente.get("/api/v1/comercios").json() == [cuerpo]


def test_un_comercio_repetido_da_409(cliente_admin: TestClient) -> None:
    cliente_admin.post("/api/v1/comercios", json={"nombre": "Walmart San Sebastián"})

    respuesta = cliente_admin.post("/api/v1/comercios", json={"nombre": "WALMART  san sebastian"})

    assert respuesta.status_code == 409


def test_el_titular_asigna_su_categoria_sugerida_a_un_comercio(
    cliente_admin: TestClient, cliente: TestClient
) -> None:
    comercio = cliente_admin.post("/api/v1/comercios", json={"nombre": "Walmart"}).json()
    categoria = _categoria(cliente)
    ruta = f"/api/v1/comercios/{comercio['id']}/categoria-sugerida"

    primera = cliente.put(ruta, json={"categoria_id": categoria["id"]})
    segunda = cliente.put(ruta, json={"categoria_id": categoria["id"]})

    assert primera.status_code == segunda.status_code == 200, "PUT es idempotente"
    assert cliente.put(ruta, json={"categoria_id": 999999}).status_code == 404
