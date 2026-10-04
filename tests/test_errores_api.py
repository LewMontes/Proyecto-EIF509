"""El manejador global de errores: todo error sale como Problem Details (RFC 9457).

Lo que estas pruebas fijan es el **contrato de error**, que es tan parte de la
API como el de las respuestas exitosas: mismo tipo de contenido, mismos cinco
miembros, y nunca una traza.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.business.errors import ErrorDeProveedorExterno
from app.business.services.categoria_service import CategoriaService
from app.data.models.usuario import Usuario
from tests.conftest import cabecera_de

MIEMBROS_ESTANDAR = {"type", "title", "status", "detail", "instance"}


def _es_un_problema(respuesta, status: int) -> dict:
    """Verifica la forma común de todo error y devuelve el cuerpo."""
    assert respuesta.status_code == status
    assert respuesta.headers["content-type"] == "application/problem+json"
    cuerpo = respuesta.json()
    assert set(cuerpo) >= MIEMBROS_ESTANDAR
    assert cuerpo["status"] == status, "el código va también en el cuerpo"
    assert cuerpo["instance"] == respuesta.request.url.path
    assert "Traceback" not in respuesta.text
    return cuerpo


# ---- un caso por código ----


def test_400_una_peticion_mal_formada_dice_que_campo_fallo(cliente: TestClient) -> None:
    """La validación de formato de los DTOs: `400`, con la lista de campos."""
    respuesta = cliente.post("/api/v1/categorias", json={"nombre": "", "color_hex": "#12"})

    cuerpo = _es_un_problema(respuesta, 400)
    assert cuerpo["type"].endswith("#solicitud-mal-formada")
    assert {error["campo"] for error in cuerpo["errores"]} == {"body.nombre", "body.color_hex"}
    assert all(error["mensaje"] for error in cuerpo["errores"])
    assert "2 campo(s)" in cuerpo["detail"]


@pytest.mark.parametrize(
    "metodo, ruta, cuerpo",
    [
        ("post", "/api/v1/categorias", {}),  # falta un campo obligatorio
        ("post", "/api/v1/categorias", {"nombre": 5, "color_hex": "#2563EB"}),  # tipo equivocado
        ("post", "/api/v1/presupuestos", {"categoria_id": 1, "anio": 2026, "mes": 13,
                                          "moneda": "CRC", "monto_limite": "100"}),  # rango
        ("post", "/api/v1/metodos-pago", {"alias": "Visa", "tipo": "BITCOIN"}),  # enum
        ("patch", "/api/v1/compras/1", {}),  # validador del modelo: al menos un campo
        ("get", "/api/v1/compras/abc", None),  # id de ruta que no es un entero
        ("get", "/api/v1/compras/99999999999999999999", None),  # id que no cabe en la columna
        ("get", "/api/v1/compras?pagina=-1", None),  # parámetro de consulta fuera de rango
        ("post", "/api/v1/usuarios", {"nombre_completo": "Ana", "correo": "a@b.cr",
                                      "contrasena": "corta"}),  # largo mínimo
    ],
)  # fmt: skip
def test_400_para_cualquier_validacion_de_formato(
    cliente: TestClient, metodo: str, ruta: str, cuerpo: dict | None
) -> None:
    respuesta = cliente.request(metodo, ruta, json=cuerpo)

    assert _es_un_problema(respuesta, 400)["errores"]


def test_400_un_cuerpo_que_no_es_json(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/v1/categorias",
        content="{esto no es json",
        headers={"Content-Type": "application/json"},
    )

    _es_un_problema(respuesta, 400)


def test_401_sin_token(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get("/api/v1/compras")

    cuerpo = _es_un_problema(respuesta, 401)
    assert cuerpo["type"].endswith("#no-autenticado")
    assert cuerpo["codigo"] == "NoAutenticado"
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


def test_401_con_credenciales_incorrectas(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "nadie@gastonomo.cr", "contrasena": "cualquiera"}
    )

    assert _es_un_problema(respuesta, 401)["codigo"] == "CredencialesInvalidas"


def test_403_cuando_el_rol_no_alcanza(cliente: TestClient) -> None:
    respuesta = cliente.post("/api/v1/comercios", json={"nombre": "Walmart"})

    cuerpo = _es_un_problema(respuesta, 403)
    assert cuerpo["type"].endswith("#acceso-denegado")
    assert cuerpo["codigo"] == "AccesoDenegado"


def test_403_cuando_el_recurso_es_de_otro(cliente: TestClient, otro_usuario: Usuario) -> None:
    respuesta = cliente.get(f"/api/v1/usuarios/{otro_usuario.id}")

    assert _es_un_problema(respuesta, 403)["detail"] == "Solo podés consultar tu propia cuenta."


def test_404_un_recurso_que_no_existe(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/compras/999999")

    cuerpo = _es_un_problema(respuesta, 404)
    assert cuerpo["type"].endswith("#recurso-no-encontrado")
    assert cuerpo["codigo"] == "RecursoNoEncontrado"
    assert "999999" in cuerpo["detail"]


def test_404_una_ruta_que_no_existe_tambien_es_un_problema(cliente: TestClient) -> None:
    """Los errores del propio framework salen con la misma forma que los del negocio."""
    cuerpo = _es_un_problema(cliente.get("/api/v1/no-existe"), 404)

    assert cuerpo["type"] == "about:blank"
    assert cuerpo["title"] == "Not Found"


def test_405_un_verbo_que_el_recurso_no_admite(cliente: TestClient) -> None:
    respuesta = cliente.put("/api/v1/compras/1", json={})

    assert _es_un_problema(respuesta, 405)["title"] == "Method Not Allowed"
    assert "GET" in respuesta.headers["allow"]


def test_409_el_codigo_dice_que_regla_de_negocio_fallo(cliente: TestClient) -> None:
    """La familia decide el código HTTP; el nombre de la regla viaja en `codigo`."""
    cliente.post("/api/v1/categorias", json={"nombre": "Alimentacion", "color_hex": "#2563EB"})

    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": "Alimentacion", "color_hex": "#2563EB"}
    )

    cuerpo = _es_un_problema(respuesta, 409)
    assert cuerpo["type"].endswith("#regla-de-negocio-violada")
    assert cuerpo["codigo"] == "NombreDuplicado"
    assert cuerpo["detail"] == "Ya existe una categoria llamada 'Alimentacion' en la cuenta."


def test_422_bien_formado_pero_rompe_una_regla_del_dominio(cliente: TestClient) -> None:
    """Siete caracteres que empiezan con `#`: el formato pasa, la regla no."""
    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": "Transporte", "color_hex": "#ZZZZZZ"}
    )

    cuerpo = _es_un_problema(respuesta, 422)
    assert cuerpo["type"].endswith("#datos-invalidos")
    assert cuerpo["codigo"] == "DatosInvalidos"
    assert "errores" not in cuerpo, "la lista de campos es solo del 400"


# ---- lo que no puede llegar al cliente ----


def test_500_un_error_inesperado_no_expone_nada_del_interior(
    aplicacion: FastAPI, usuario: Usuario
) -> None:
    cliente = TestClient(aplicacion, headers=cabecera_de(usuario), raise_server_exceptions=False)
    secreto = "postgresql://gastonomo:clave-secreta@db-interna:5432"

    with patch.object(
        CategoriaService, "listar_activas", side_effect=RuntimeError(f"no conecta a {secreto}")
    ):
        respuesta = cliente.get("/api/v1/categorias")

    cuerpo = _es_un_problema(respuesta, 500)
    assert cuerpo["type"].endswith("#error-interno")
    for fuga in ("RuntimeError", "clave-secreta", "db-interna", "listar_activas", ".py"):
        assert fuga not in respuesta.text
    assert "codigo" not in cuerpo


def test_un_choque_de_integridad_de_la_base_da_409_sin_nombrar_tablas(
    aplicacion: FastAPI, usuario: Usuario
) -> None:
    """Dos peticiones simultáneas que pasan la misma validación: la segunda choca en la base."""
    cliente = TestClient(aplicacion, headers=cabecera_de(usuario), raise_server_exceptions=False)
    error = IntegrityError("INSERT INTO categoria ...", {}, Exception("uq_categoria_nombre"))

    with patch.object(CategoriaService, "crear", side_effect=error):
        respuesta = cliente.post(
            "/api/v1/categorias", json={"nombre": "Alimentacion", "color_hex": "#2563EB"}
        )

    _es_un_problema(respuesta, 409)
    assert "uq_categoria" not in respuesta.text and "INSERT" not in respuesta.text


def test_502_cuando_falla_un_proveedor_externo(aplicacion: FastAPI, usuario: Usuario) -> None:
    cliente = TestClient(aplicacion, headers=cabecera_de(usuario))

    with patch.object(
        CategoriaService, "listar_activas", side_effect=ErrorDeProveedorExterno("BCCR no responde")
    ):
        respuesta = cliente.get("/api/v1/categorias")

    assert _es_un_problema(respuesta, 502)["type"].endswith("#proveedor-externo")


# ---- el contrato documentado ----


def test_el_contrato_openapi_declara_los_errores_como_problem_details(
    cliente_anonimo: TestClient,
) -> None:
    esquema = cliente_anonimo.get("/openapi.json").json()
    respuestas = esquema["paths"]["/api/v1/compras"]["post"]["responses"]

    assert {"201", "400", "401", "403", "404", "409", "422"} <= set(respuestas)
    for codigo in ("400", "401", "403", "404", "409", "422"):
        contenido = respuestas[codigo]["content"]["application/problem+json"]
        assert contenido["schema"]["$ref"].endswith("/ProblemDetail")
    # El `HTTPValidationError` que FastAPI documenta por defecto ya no describe
    # lo que esta API devuelve: no tiene que quedar en el contrato.
    assert "HTTPValidationError" not in esquema["components"]["schemas"]


def test_el_contrato_declara_el_esquema_de_seguridad_bearer(cliente_anonimo: TestClient) -> None:
    esquema = cliente_anonimo.get("/openapi.json").json()

    (seguridad,) = esquema["components"]["securitySchemes"].values()
    assert (seguridad["type"], seguridad["scheme"], seguridad["bearerFormat"]) == (
        "http",
        "bearer",
        "JWT",
    )
    assert esquema["paths"]["/api/v1/compras"]["get"]["security"], "protegido"
    assert "security" not in esquema["paths"]["/api/v1/auth/login"]["post"], "público"
    assert "security" not in esquema["paths"]["/api/v1/usuarios"]["post"], "público"


def test_swagger_ui_esta_operativa(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get("/docs")

    assert respuesta.status_code == 200
    assert "swagger-ui" in respuesta.text
