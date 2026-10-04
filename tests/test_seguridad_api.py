"""La seguridad de la API: login, token, roles y propiedad del recurso.

Las tres preguntas que la API se hace en cada petición, en este orden:

1. **¿Quién sos?** Sin un token válido, `401`.
2. **¿Tu rol alcanza?** Un titular en un endpoint de administrador, `403`.
3. **¿Esto es tuyo?** Lo verifica el servicio, no el router: lo ajeno no se ve.
"""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.business.seguridad.contrasenas import hashear_contrasena
from app.config.settings import obtener_configuracion
from app.data.models.usuario import Usuario
from tests.conftest import COSTO_DE_HASH_EN_PRUEBAS

CONTRASENA = "una-clave-larga"


def _registrar(cliente: TestClient, correo: str = "ana@gastonomo.cr") -> dict:
    respuesta = cliente.post(
        "/api/v1/usuarios",
        json={"nombre_completo": "Ana Mora", "correo": correo, "contrasena": CONTRASENA},
    )
    assert respuesta.status_code == 201
    return respuesta.json()


# ---- registro y login ----


def test_registrarse_es_publico_y_devuelve_201_con_location(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.post(
        "/api/v1/usuarios",
        json={
            "nombre_completo": "Ana Mora",
            "correo": "Ana@Gastonomo.cr",
            "contrasena": CONTRASENA,
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert respuesta.headers["Location"] == f"/api/v1/usuarios/{cuerpo['id']}"
    assert cuerpo["correo"] == "ana@gastonomo.cr", "el correo se guarda en minúsculas"
    assert cuerpo["rol"] == "TITULAR", "toda cuenta nace TITULAR"
    assert "contrasena" not in cuerpo and "contrasena_hash" not in cuerpo


def test_no_se_puede_pedir_el_rol_al_registrarse(cliente_anonimo: TestClient) -> None:
    """Si el rol se pudiera elegir, cualquiera se registraría como administrador."""
    respuesta = cliente_anonimo.post(
        "/api/v1/usuarios",
        json={
            "nombre_completo": "Ana Mora",
            "correo": "ana@gastonomo.cr",
            "contrasena": CONTRASENA,
            "rol": "ADMIN",
        },
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "TITULAR"


def test_un_correo_repetido_da_409(cliente_anonimo: TestClient) -> None:
    _registrar(cliente_anonimo)

    respuesta = cliente_anonimo.post(
        "/api/v1/usuarios",
        json={"nombre_completo": "Otra", "correo": "ana@gastonomo.cr", "contrasena": CONTRASENA},
    )

    assert respuesta.status_code == 409


def test_el_login_emite_un_token_que_sirve_para_entrar(cliente_anonimo: TestClient) -> None:
    creado = _registrar(cliente_anonimo)

    login = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "ana@gastonomo.cr", "contrasena": CONTRASENA}
    )

    assert login.status_code == 200
    cuerpo = login.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["expires_in"] > 0
    assert cuerpo["rol"] == "TITULAR"

    yo = cliente_anonimo.get(
        "/api/v1/usuarios/yo", headers={"Authorization": f"Bearer {cuerpo['access_token']}"}
    )
    assert yo.status_code == 200
    assert yo.json()["id"] == creado["id"]


def test_el_token_lleva_el_titular_y_el_rol_pero_ningun_dato_sensible(
    cliente_anonimo: TestClient,
) -> None:
    creado = _registrar(cliente_anonimo)
    token = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "ana@gastonomo.cr", "contrasena": CONTRASENA}
    ).json()["access_token"]

    contenido = jwt.decode(token, obtener_configuracion().jwt_secreto, algorithms=["HS256"])

    assert contenido["sub"] == str(creado["id"])
    assert contenido["rol"] == "TITULAR"
    assert set(contenido) == {"sub", "rol", "iat", "exp"}


def test_una_contrasena_equivocada_da_401_sin_decir_que_fallo(
    cliente_anonimo: TestClient,
) -> None:
    _registrar(cliente_anonimo)

    mala = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "ana@gastonomo.cr", "contrasena": "otra-clave"}
    )
    inexistente = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "nadie@gastonomo.cr", "contrasena": CONTRASENA}
    )

    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json(), "el mismo error para los dos casos"
    assert mala.headers["WWW-Authenticate"] == "Bearer"


def test_una_cuenta_desactivada_no_inicia_sesion(
    cliente_anonimo: TestClient, sesion: Session
) -> None:
    sesion.add(
        Usuario(
            nombre_completo="Inactiva",
            correo="inactiva@gastonomo.cr",
            contrasena_hash=hashear_contrasena(CONTRASENA, COSTO_DE_HASH_EN_PRUEBAS),
            activo=False,
        )
    )
    sesion.commit()

    respuesta = cliente_anonimo.post(
        "/api/v1/auth/login", json={"correo": "inactiva@gastonomo.cr", "contrasena": CONTRASENA}
    )

    assert respuesta.status_code == 401


# ---- 401: sin identidad ----


def test_sin_token_da_401(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get("/api/v1/categorias")

    assert respuesta.status_code == 401
    assert respuesta.headers["WWW-Authenticate"] == "Bearer"


def test_un_token_alterado_da_401(cliente_anonimo: TestClient) -> None:
    respuesta = cliente_anonimo.get(
        "/api/v1/categorias", headers={"Authorization": "Bearer esto.no.es-un-jwt"}
    )

    assert respuesta.status_code == 401


def test_un_token_firmado_con_otra_clave_da_401(
    cliente_anonimo: TestClient, usuario: Usuario
) -> None:
    """Cualquiera puede armar un JWT; lo que no puede es firmarlo con nuestra clave."""
    falso = jwt.encode(
        {"sub": str(usuario.id), "rol": "ADMIN", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "una-clave-que-no-es-la-del-servidor-aunque-sea-larga",
        algorithm="HS256",
    )

    respuesta = cliente_anonimo.get(
        "/api/v1/usuarios", headers={"Authorization": f"Bearer {falso}"}
    )

    assert respuesta.status_code == 401


def test_un_token_vencido_da_401(cliente_anonimo: TestClient, usuario: Usuario) -> None:
    vencido = jwt.encode(
        {
            "sub": str(usuario.id),
            "rol": "TITULAR",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        obtener_configuracion().jwt_secreto,
        algorithm="HS256",
    )

    respuesta = cliente_anonimo.get(
        "/api/v1/categorias", headers={"Authorization": f"Bearer {vencido}"}
    )

    assert respuesta.status_code == 401
    assert "venció" in respuesta.json()["detail"]


def test_el_token_de_una_cuenta_desactivada_deja_de_valer(
    cliente: TestClient, usuario: Usuario, sesion: Session
) -> None:
    """Por eso la cuenta se relee en cada petición: no hay que esperar a que venza."""
    assert cliente.get("/api/v1/categorias").status_code == 200

    usuario.activo = False
    sesion.commit()

    assert cliente.get("/api/v1/categorias").status_code == 401


def test_el_endpoint_de_salud_no_pide_token(cliente_anonimo: TestClient) -> None:
    assert cliente_anonimo.get("/api/salud").status_code == 200


# ---- 403: el rol no alcanza ----


def test_un_titular_no_lista_las_cuentas(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/usuarios")

    assert respuesta.status_code == 403
    assert "ADMIN" in respuesta.json()["detail"]


def test_un_administrador_si_lista_las_cuentas(cliente_admin: TestClient, usuario: Usuario) -> None:
    respuesta = cliente_admin.get("/api/v1/usuarios")

    assert respuesta.status_code == 200
    assert {cuenta["correo"] for cuenta in respuesta.json()["contenido"]} == {
        "admin@gastonomo.cr",
        usuario.correo,
    }


def test_un_titular_no_da_de_alta_comercios_en_el_catalogo_compartido(
    cliente: TestClient,
) -> None:
    respuesta = cliente.post("/api/v1/comercios", json={"nombre": "Walmart San Sebastián"})

    assert respuesta.status_code == 403


def test_si_el_rol_cambia_en_la_base_el_token_viejo_ya_no_autoriza(
    cliente_admin: TestClient, administrador: Usuario, sesion: Session
) -> None:
    """El token dice ADMIN, pero el rol que vale es el de la base."""
    from app.data.models.enums import RolUsuario

    assert cliente_admin.get("/api/v1/usuarios").status_code == 200

    administrador.rol = RolUsuario.TITULAR
    sesion.commit()

    assert cliente_admin.get("/api/v1/usuarios").status_code == 403


# ---- propiedad del recurso (OWASP API1) ----


def test_un_titular_consulta_su_propia_cuenta(cliente: TestClient, usuario: Usuario) -> None:
    respuesta = cliente.get(f"/api/v1/usuarios/{usuario.id}")

    assert respuesta.status_code == 200
    assert respuesta.json()["correo"] == usuario.correo


def test_un_titular_no_consulta_la_cuenta_de_otro(
    cliente: TestClient, otro_usuario: Usuario
) -> None:
    respuesta = cliente.get(f"/api/v1/usuarios/{otro_usuario.id}")

    assert respuesta.status_code == 403


def test_pedir_una_cuenta_ajena_que_no_existe_tambien_da_403(cliente: TestClient) -> None:
    """Si diera 404, un titular podría enumerar qué ids de cuenta existen."""
    assert cliente.get("/api/v1/usuarios/999999").status_code == 403


def test_un_administrador_consulta_cualquier_cuenta(
    cliente_admin: TestClient, usuario: Usuario
) -> None:
    assert cliente_admin.get(f"/api/v1/usuarios/{usuario.id}").status_code == 200
    assert cliente_admin.get("/api/v1/usuarios/999999").status_code == 404


def test_la_categoria_de_otro_titular_no_se_ve_ni_se_toca(
    aplicacion, cliente: TestClient, otro_usuario: Usuario
) -> None:
    """El `usuario_id` sale del token: no hay forma de pedir a nombre de otro.

    Lo ajeno responde `404`, igual que lo que no existe -el servicio busca por
    id **y** por dueño a la vez-, para no confirmar que el recurso existe.
    """
    from tests.conftest import cabecera_de

    ajena = TestClient(aplicacion, headers=cabecera_de(otro_usuario)).post(
        "/api/v1/categorias", json={"nombre": "Privada", "color_hex": "#111111"}
    )
    categoria_id = ajena.json()["id"]

    assert cliente.get(f"/api/v1/categorias/{categoria_id}").status_code == 404
    assert cliente.delete(f"/api/v1/categorias/{categoria_id}").status_code == 404
    assert (
        cliente.put(
            f"/api/v1/categorias/{categoria_id}", json={"nombre": "Mía", "color_hex": "#222222"}
        ).status_code
        == 404
    )
    assert cliente.get("/api/v1/categorias").json() == []


def test_mandar_usuario_id_en_el_cuerpo_no_cambia_el_dueno(
    cliente: TestClient, usuario: Usuario, otro_usuario: Usuario
) -> None:
    respuesta = cliente.post(
        "/api/v1/categorias",
        json={"usuario_id": otro_usuario.id, "nombre": "Alimentacion", "color_hex": "#2563EB"},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["usuario_id"] == usuario.id
