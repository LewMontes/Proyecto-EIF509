"""La API de punta a punta contra PostgreSQL real: los códigos de estado del contrato.

Cada prueba hace una petición HTTP a la aplicación verdadera, que corre sobre
un `postgres:16-alpine` levantado con Testcontainers y con el esquema de las
migraciones de Flyway (`V1`…`V8`). No hay SQLite ni dobles de repositorio: lo
que responde es el recorrido completo -router, dependencia de seguridad,
servicio, repositorio y la base con sus restricciones reales.

Están agrupadas por el código que verifican, que es lo que pide el enunciado:
**201, 400, 401, 403, 404 y 422** como mínimo, más el 204 y el 409 del diseño
REST. Y al final, los dos procesos del dominio completos.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.data.models.compra import Compra
from app.data.models.comprobante import Comprobante
from app.data.models.enums import EstadoComprobante
from app.data.models.usuario import Usuario
from tests.integracion.conftest import CONTRASENA_DE_PRUEBA

pytestmark = pytest.mark.integracion

PROBLEMA = "application/problem+json"


# ---- armado de datos, siempre por la API ----


def _categoria(api: TestClient, nombre: str = "Supermercado") -> dict:
    respuesta = api.post("/api/v1/categorias", json={"nombre": nombre, "color_hex": "#16A34A"})
    assert respuesta.status_code == 201
    return respuesta.json()


def _comercio(api_admin: TestClient, nombre: str = "Walmart San Sebastián") -> dict:
    respuesta = api_admin.post("/api/v1/comercios", json={"nombre": nombre})
    assert respuesta.status_code == 201
    return respuesta.json()


def _buzon(api: TestClient) -> int:
    respuesta = api.post(
        "/api/v1/cuentas-correo", json={"proveedor": "GMAIL", "direccion": "titular@gmail.com"}
    )
    assert respuesta.status_code == 201
    return respuesta.json()["id"]


def _compra(comercio_id: int, categoria_id: int | None, **extra) -> dict:
    linea = {"descripcion": "Leche 1L", "cantidad": "2", "precio_unitario": "1000.00"}
    if categoria_id is not None:
        linea["categoria_id"] = categoria_id
    return {"comercio_id": comercio_id, "fecha": "2026-08-30", "lineas": [linea], **extra}


def _comprobante(buzon: int, **extra) -> dict:
    return {
        "cuenta_correo_id": buzon,
        "mensaje_id": "AAMk-0001",
        "remitente": "notificacion@baccredomatic.cr",
        "banco": "BAC Credomatic",
        "comercio": "WALMART SAN SEBASTIAN",
        "monto": "7870.00",
        "moneda": "CRC",
        "fecha": "2026-08-30T13:27:00",
        "ultimos_cuatro": "4321",
        **extra,
    }


# ============================================================================
#  201 Created (+ Location)
# ============================================================================


def test_201_registrarse_e_iniciar_sesion_contra_la_base_real(api_anonima: TestClient) -> None:
    """El flujo de seguridad completo: registro, login con bcrypt y uso del token."""
    registro = api_anonima.post(
        "/api/v1/usuarios",
        json={
            "nombre_completo": "Ana Mora",
            "correo": "ana@gastonomo.cr",
            "contrasena": CONTRASENA_DE_PRUEBA,
        },
    )
    assert registro.status_code == 201
    assert registro.headers["Location"] == f"/api/v1/usuarios/{registro.json()['id']}"
    assert registro.json()["rol"] == "TITULAR"

    login = api_anonima.post(
        "/api/v1/auth/login",
        json={"correo": "ana@gastonomo.cr", "contrasena": CONTRASENA_DE_PRUEBA},
    )
    assert login.status_code == 200
    cabecera = {"Authorization": f"Bearer {login.json()['access_token']}"}

    yo = api_anonima.get("/api/v1/usuarios/yo", headers=cabecera)
    assert yo.status_code == 200
    assert yo.json()["correo"] == "ana@gastonomo.cr"


@pytest.mark.parametrize(
    "recurso, cuerpo",
    [
        ("categorias", {"nombre": "Supermercado", "color_hex": "#16A34A"}),
        ("metodos-pago", {"alias": "Visa BAC", "tipo": "CREDITO", "ultimos_cuatro": "4321"}),
        ("cuentas-correo", {"proveedor": "OUTLOOK", "direccion": "titular@outlook.com"}),
    ],
)
def test_201_crear_devuelve_location_y_el_recurso_se_puede_consultar(
    api: TestClient, recurso: str, cuerpo: dict
) -> None:
    respuesta = api.post(f"/api/v1/{recurso}", json=cuerpo)

    assert respuesta.status_code == 201
    ubicacion = respuesta.headers["Location"]
    assert ubicacion == f"/api/v1/{recurso}/{respuesta.json()['id']}"
    consulta = api.get(ubicacion)
    assert consulta.status_code == 200
    assert consulta.json() == respuesta.json()


def test_201_un_administrador_da_de_alta_un_comercio(api_admin: TestClient) -> None:
    respuesta = api_admin.post(
        "/api/v1/comercios",
        json={"nombre": "Walmart San Sebastián", "identificacion_tributaria": "3101007223"},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["nombre_normalizado"] == "WALMART SAN SEBASTIAN"


# ============================================================================
#  204 No Content
# ============================================================================


def test_204_desactivar_no_devuelve_cuerpo(api: TestClient) -> None:
    categoria = _categoria(api)

    respuesta = api.delete(f"/api/v1/categorias/{categoria['id']}")

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert api.get(f"/api/v1/categorias/{categoria['id']}").json()["activa"] is False


# ============================================================================
#  400 Bad Request
# ============================================================================


@pytest.mark.parametrize(
    "cuerpo, campo",
    [
        ({"nombre": "", "color_hex": "#16A34A"}, "body.nombre"),
        ({"color_hex": "#16A34A"}, "body.nombre"),
        ({"nombre": "Super", "color_hex": "#16A34A", "categoria_padre_id": 0},
         "body.categoria_padre_id"),
    ],
)  # fmt: skip
def test_400_un_dto_mal_formado_no_llega_a_la_base(
    api: TestClient, sesion_de_la_api: Session, cuerpo: dict, campo: str
) -> None:
    respuesta = api.post("/api/v1/categorias", json=cuerpo)

    assert respuesta.status_code == 400
    assert respuesta.headers["content-type"] == PROBLEMA
    assert [error["campo"] for error in respuesta.json()["errores"]] == [campo]
    assert sesion_de_la_api.scalar(text("SELECT count(*) FROM categoria")) == 0


def test_400_un_comprobante_con_monto_negativo_o_fecha_futura(api: TestClient) -> None:
    buzon = _buzon(api)

    negativo = api.post("/api/v1/comprobantes", json=_comprobante(buzon, monto="-1.00"))
    futuro = api.post("/api/v1/comprobantes", json=_comprobante(buzon, fecha="2999-01-01T00:00:00"))
    sin_moneda = api.post("/api/v1/comprobantes", json=_comprobante(buzon, moneda="XYZ"))

    assert (negativo.status_code, futuro.status_code, sin_moneda.status_code) == (400, 400, 400)
    assert api.get("/api/v1/comprobantes").json()["total_elementos"] == 0


def test_400_un_orden_por_un_campo_que_no_existe(api: TestClient) -> None:
    respuesta = api.get("/api/v1/compras", params={"orden": "contrasena_hash,desc"})

    assert respuesta.status_code == 400
    assert respuesta.json()["errores"][0]["campo"] == "query.orden.0"


# ============================================================================
#  401 Unauthorized
# ============================================================================


@pytest.mark.parametrize(
    "metodo, ruta",
    [
        ("get", "/api/v1/categorias"),
        ("get", "/api/v1/compras"),
        ("post", "/api/v1/compras"),
        ("post", "/api/v1/comprobantes"),
        ("get", "/api/v1/usuarios"),
        ("get", "/api/v1/usuarios/yo"),
        ("delete", "/api/v1/presupuestos/1"),
    ],
)
def test_401_sin_token_ningun_endpoint_de_negocio_responde(
    api_anonima: TestClient, metodo: str, ruta: str
) -> None:
    respuesta = api_anonima.request(metodo, ruta, json={})

    assert respuesta.status_code == 401
    assert respuesta.headers["content-type"] == PROBLEMA
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


def test_401_con_la_contrasena_equivocada(api_anonima: TestClient, titular: Usuario) -> None:
    respuesta = api_anonima.post(
        "/api/v1/auth/login", json={"correo": titular.correo, "contrasena": "no-es-la-clave"}
    )

    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "CredencialesInvalidas"


def test_401_con_un_token_que_no_firmo_este_servidor(api_anonima: TestClient) -> None:
    respuesta = api_anonima.get(
        "/api/v1/compras", headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.e30.firma"}
    )

    assert respuesta.status_code == 401


# ============================================================================
#  403 Forbidden
# ============================================================================


def test_403_un_titular_no_entra_a_los_endpoints_de_administrador(api: TestClient) -> None:
    listar = api.get("/api/v1/usuarios")
    alta = api.post("/api/v1/comercios", json={"nombre": "Walmart"})

    assert (listar.status_code, alta.status_code) == (403, 403)
    assert listar.headers["content-type"] == PROBLEMA
    assert listar.json()["codigo"] == "AccesoDenegado"


def test_403_un_titular_no_consulta_la_cuenta_de_otro(
    api: TestClient, api_admin: TestClient, otro_titular: Usuario
) -> None:
    """La propiedad del recurso la verifica el servicio; el administrador sí puede."""
    assert api.get(f"/api/v1/usuarios/{otro_titular.id}").status_code == 403
    assert api_admin.get(f"/api/v1/usuarios/{otro_titular.id}").status_code == 200


# ============================================================================
#  404 Not Found
# ============================================================================


@pytest.mark.parametrize(
    "recurso",
    ["categorias", "metodos-pago", "presupuestos", "reglas-categorizacion", "compras",
     "comprobantes", "cuentas-correo", "comercios"],
)  # fmt: skip
def test_404_un_recurso_que_no_existe(api: TestClient, recurso: str) -> None:
    respuesta = api.get(f"/api/v1/{recurso}/999999")

    assert respuesta.status_code == 404
    assert respuesta.headers["content-type"] == PROBLEMA
    assert respuesta.json()["codigo"] == "RecursoNoEncontrado"


def test_404_lo_de_otro_titular_es_indistinguible_de_lo_que_no_existe(
    api: TestClient, api_de_otro: TestClient, api_admin: TestClient
) -> None:
    """OWASP API1: pedir por id un recurso ajeno no confirma ni que existe."""
    comercio = _comercio(api_admin)
    categoria = _categoria(api)
    compra_id = api.post("/api/v1/compras", json=_compra(comercio["id"], categoria["id"])).json()[
        "compra_id"
    ]

    assert api_de_otro.get(f"/api/v1/compras/{compra_id}").status_code == 404
    assert api_de_otro.delete(f"/api/v1/compras/{compra_id}").status_code == 404
    assert api_de_otro.get(f"/api/v1/categorias/{categoria['id']}").status_code == 404
    # Tampoco puede usar la categoría ajena en una compra propia.
    ajena = api_de_otro.post("/api/v1/compras", json=_compra(comercio["id"], categoria["id"]))
    assert ajena.status_code == 404
    assert api_de_otro.get("/api/v1/compras").json()["total_elementos"] == 0
    assert api.get(f"/api/v1/compras/{compra_id}").status_code == 200


# ============================================================================
#  409 Conflict
# ============================================================================


def test_409_un_nombre_repetido(api: TestClient) -> None:
    _categoria(api, "Supermercado")

    respuesta = api.post(
        "/api/v1/categorias", json={"nombre": "Supermercado", "color_hex": "#16A34A"}
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "NombreDuplicado"


def test_409_una_categoria_padre_no_recibe_gasto(api: TestClient, api_admin: TestClient) -> None:
    comercio = _comercio(api_admin)
    padre = _categoria(api, "Alimentacion")
    api.post(
        "/api/v1/categorias",
        json={"nombre": "Supermercado", "color_hex": "#16A34A", "categoria_padre_id": padre["id"]},
    )

    respuesta = api.post("/api/v1/compras", json=_compra(comercio["id"], padre["id"]))

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "CategoriaNoEsHoja"


# ============================================================================
#  422 Unprocessable Content
# ============================================================================


def test_422_un_dato_bien_formado_que_rompe_una_regla_del_dominio(api: TestClient) -> None:
    respuesta = api.post("/api/v1/categorias", json={"nombre": "Super", "color_hex": "#ZZZZZZ"})

    assert respuesta.status_code == 422
    assert respuesta.headers["content-type"] == PROBLEMA
    assert respuesta.json()["codigo"] == "DatosInvalidos"


def test_422_una_compra_en_dolares_sin_su_tipo_de_cambio(
    api: TestClient, api_admin: TestClient
) -> None:
    comercio = _comercio(api_admin)
    categoria = _categoria(api)

    respuesta = api.post(
        "/api/v1/compras", json=_compra(comercio["id"], categoria["id"], moneda="USD")
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "TipoDeCambioRequerido"


def test_422_un_rango_de_fechas_invertido(api: TestClient) -> None:
    respuesta = api.get("/api/v1/compras", params={"desde": "2026-09-30", "hasta": "2026-09-01"})

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "RangoInvalido"


# ============================================================================
#  Los dos procesos, completos, contra el esquema de Flyway
# ============================================================================


def test_proceso_1_registrar_corregir_y_anular_una_compra(
    api: TestClient, api_admin: TestClient
) -> None:
    comercio = _comercio(api_admin)
    categoria = _categoria(api)
    presupuesto = api.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria["id"],
            "anio": 2026,
            "mes": 8,
            "moneda": "CRC",
            "monto_limite": "100000.00",
        },
    ).json()
    ruta_presupuesto = f"/api/v1/presupuestos/{presupuesto['id']}"

    registro = api.post("/api/v1/compras", json=_compra(comercio["id"], categoria["id"]))

    assert registro.status_code == 201
    compra = registro.json()
    assert registro.headers["Location"] == f"/api/v1/compras/{compra['compra_id']}"
    assert Decimal(compra["total"]) == Decimal("2260.00")
    assert Decimal(api.get(ruta_presupuesto).json()["monto_consumido"]) == Decimal("2260.00")

    metodo = api.post("/api/v1/metodos-pago", json={"alias": "Efectivo", "tipo": "EFECTIVO"}).json()
    corregida = api.patch(
        f"/api/v1/compras/{compra['compra_id']}", json={"metodo_pago_id": metodo["id"]}
    )
    assert corregida.status_code == 200
    assert corregida.json()["metodo_pago_alias"] == "Efectivo"

    assert api.delete(f"/api/v1/compras/{compra['compra_id']}").status_code == 204
    assert Decimal(api.get(ruta_presupuesto).json()["monto_consumido"]) == Decimal("0.00")
    assert api.get(f"/api/v1/compras/{compra['compra_id']}").json()["estado"] == "ANULADA"
    assert api.delete(f"/api/v1/compras/{compra['compra_id']}").status_code == 409


def test_proceso_2_un_comprobante_escribe_las_cinco_tablas(
    api: TestClient, sesion_de_la_api: Session
) -> None:
    """La transacción de la conciliación, disparada por HTTP, sobre el esquema real.

    Pasa por las llaves foráneas compuestas de `V3` -el renglón y el comprobante
    tienen que ser del mismo titular que la compra- y por el `CHECK` que exige
    que un comprobante `PROCESADO` tenga su compra.
    """
    buzon = _buzon(api)
    categoria = _categoria(api)
    api.post(
        "/api/v1/metodos-pago",
        json={"alias": "Visa BAC", "tipo": "CREDITO", "ultimos_cuatro": "4321"},
    )
    regla = api.post(
        "/api/v1/reglas-categorizacion",
        json={"nombre": "Walmart", "patron": "WALMART", "categoria_destino_id": categoria["id"]},
    ).json()
    presupuesto = api.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria["id"],
            "anio": 2026,
            "mes": 8,
            "moneda": "CRC",
            "monto_limite": "9000.00",
        },
    ).json()

    respuesta = api.post("/api/v1/comprobantes", json=_comprobante(buzon))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert respuesta.headers["Location"] == f"/api/v1/comprobantes/{cuerpo['id']}"
    assert cuerpo["estado"] == "PROCESADO"

    compra = api.get(f"/api/v1/compras/{cuerpo['compra_id']}").json()
    assert compra["origen"] == "INGESTA_CORREO"
    assert compra["categoria_nombre"] == "Supermercado"
    assert compra["metodo_pago_alias"] == "Visa BAC"
    assert compra["requiere_revision"] is False
    consumido = api.get(f"/api/v1/presupuestos/{presupuesto['id']}").json()["monto_consumido"]
    assert Decimal(consumido) == Decimal("7870.00")
    assert api.get(f"/api/v1/reglas-categorizacion/{regla['id']}").json()["veces_aplicada"] == 1

    # Y lo mismo, leído directo de la base.
    fila = sesion_de_la_api.scalars(select(Comprobante)).one()
    assert fila.estado == EstadoComprobante.PROCESADO
    assert fila.compra_id == cuerpo["compra_id"]
    assert sesion_de_la_api.scalars(select(Compra)).one().usuario_id == fila.usuario_id

    # La idempotencia la garantiza el servicio antes que el UNIQUE de la base.
    assert api.post("/api/v1/comprobantes", json=_comprobante(buzon)).status_code == 409
    assert api.get("/api/v1/compras").json()["total_elementos"] == 1


def test_proceso_2_en_dolares_sin_tipo_de_cambio_queda_pendiente(api: TestClient) -> None:
    buzon = _buzon(api)

    respuesta = api.post(
        "/api/v1/comprobantes", json=_comprobante(buzon, moneda="USD", monto="10.00")
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "PARSEADO"
    assert respuesta.json()["compra_id"] is None
    assert api.get("/api/v1/compras").json()["total_elementos"] == 0


# ============================================================================
#  La colección paginada, con el `COUNT` y el `ORDER BY` de PostgreSQL
# ============================================================================


def test_la_coleccion_de_compras_se_pagina_ordena_y_filtra(
    api: TestClient, api_admin: TestClient
) -> None:
    comercio = _comercio(api_admin)
    supermercado, farmacia = _categoria(api, "Supermercado"), _categoria(api, "Farmacia")
    for dia, categoria in ((1, supermercado), (5, supermercado), (9, farmacia)):
        cuerpo = _compra(comercio["id"], categoria["id"], fecha=f"2026-08-{dia:02d}")
        assert api.post("/api/v1/compras", json=cuerpo).status_code == 201

    primera = api.get("/api/v1/compras", params={"tamano": 2, "orden": "fecha,asc"}).json()
    filtrada = api.get(
        "/api/v1/compras",
        params={"categoria_id": supermercado["id"], "desde": "2026-08-02", "hasta": "2026-08-31"},
    ).json()

    assert [compra["fecha"] for compra in primera["contenido"]] == ["2026-08-01", "2026-08-05"]
    assert (primera["total_elementos"], primera["total_paginas"]) == (3, 2)
    assert (primera["primera"], primera["ultima"]) == (True, False)
    assert [compra["fecha"] for compra in filtrada["contenido"]] == ["2026-08-05"]
    assert filtrada["total_elementos"] == 1
