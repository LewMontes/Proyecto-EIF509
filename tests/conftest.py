"""Piezas compartidas por las pruebas.

Las pruebas corren contra una base SQLite en memoria: se crea vacia para cada
prueba y desaparece al terminar. Asi la suite no depende de que haya un servidor
de base de datos levantado, ni en la maquina de nadie ni en la CI.

Lo que estas fixtures **no** prueban es la base misma -SQLite guarda `NUMERIC`
como punto flotante, ignora el largo de un `VARCHAR` y no aplica
`ON DELETE CASCADE`. Para eso estan las pruebas de `tests/integracion/`, que
levantan un PostgreSQL real con Testcontainers y traen sus propias fixtures.

La API exige un token en casi todos sus endpoints, asi que hay tres clientes:
`cliente` (autenticado como el titular de la prueba, el que usa casi todo),
`cliente_admin` y `cliente_anonimo`.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.seguridad.tokens import emitir_token
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.usuario_service import UsuarioService
from app.config.database import obtener_sesion
from app.config.settings import obtener_configuracion
from app.data.models import Base, Usuario
from app.data.models.enums import RolUsuario
from app.data.repositories.bitacora_repository import BitacoraRepository
from app.data.repositories.usuario_repository import UsuarioRepository
from app.main import crear_app
from app.presentation.dependencies import (
    obtener_servicio_de_bitacora,
    obtener_servicio_de_tipo_cambio,
    obtener_servicio_de_usuarios,
)

# El costo minimo que bcrypt acepta. El de produccion (12) le suma un cuarto
# de segundo a cada cuenta que una prueba registra por la API, sin probar nada.
COSTO_DE_HASH_EN_PRUEBAS = 4


def _bitacora_sin_mongo() -> BitacoraComprasService:
    """Bitacora con un repositorio sin coleccion: cualquier llamado es un no-op."""
    return BitacoraComprasService(BitacoraRepository(None))


def cabecera_de(usuario: Usuario) -> dict[str, str]:
    """El encabezado `Authorization` de un token valido para ese usuario.

    Firma el token directo, sin pasar por el login: lo que estas pruebas
    quieren es llegar autenticadas al endpoint que prueban. El login tiene sus
    propias pruebas.
    """
    configuracion = obtener_configuracion()
    token = emitir_token(usuario.id, usuario.rol, configuracion.jwt_secreto, minutos=5)
    return {"Authorization": f"Bearer {token.access_token}"}


@pytest.fixture
def sesion() -> Iterator[Session]:
    """Sesion contra una base en memoria, nueva para cada prueba.

    StaticPool obliga a que todas las conexiones compartan la misma base en
    memoria; sin el, cada conexion nueva arrancaria con una base vacia distinta.
    """
    motor = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    fabrica = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)

    with fabrica() as sesion_de_prueba:
        yield sesion_de_prueba

    Base.metadata.drop_all(motor)


@pytest.fixture
def usuario(sesion: Session) -> Usuario:
    """Un titular ya guardado, dueno de los datos de la prueba."""
    nuevo = Usuario(nombre_completo="Usuario de prueba", correo="prueba@est.una.ac.cr")
    sesion.add(nuevo)
    sesion.commit()
    return nuevo


@pytest.fixture
def otro_usuario(sesion: Session) -> Usuario:
    """Un segundo titular, para probar que nadie ve ni toca lo de otro."""
    nuevo = Usuario(nombre_completo="Otra persona", correo="otra@est.una.ac.cr")
    sesion.add(nuevo)
    sesion.commit()
    return nuevo


@pytest.fixture
def administrador(sesion: Session) -> Usuario:
    """Una cuenta con rol ADMIN."""
    nuevo = Usuario(
        nombre_completo="Administracion", correo="admin@gastonomo.cr", rol=RolUsuario.ADMIN
    )
    sesion.add(nuevo)
    sesion.commit()
    return nuevo


@pytest.fixture
def aplicacion(sesion: Session) -> Iterator[FastAPI]:
    """La app real, pero apuntando a la base en memoria y sin salir a la red.

    Reemplaza tres dependencias:

    - La **bitacora**, por una sin coleccion: sin esto, cualquier prueba que
      tocara una compra se quedaria intentando conectar a un Mongo que no
      existe en la CI durante los 3 segundos del timeout.
    - El **tipo de cambio**, por ninguno: el de verdad le pregunta al Banco
      Central por HTTP. Una prueba que necesite una tasa pisa este override
      con su propio doble.
    - El **servicio de cuentas**, por uno con el hash barato.
    """
    app = crear_app()
    app.dependency_overrides[obtener_sesion] = lambda: sesion
    app.dependency_overrides[obtener_servicio_de_bitacora] = _bitacora_sin_mongo
    app.dependency_overrides[obtener_servicio_de_tipo_cambio] = lambda: None
    app.dependency_overrides[obtener_servicio_de_usuarios] = lambda: UsuarioService(
        UsuarioRepository(sesion), costo_del_hash=COSTO_DE_HASH_EN_PRUEBAS
    )

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
def cliente(aplicacion: FastAPI, usuario: Usuario) -> TestClient:
    """Cliente HTTP autenticado como el titular de la prueba."""
    return TestClient(aplicacion, headers=cabecera_de(usuario))


@pytest.fixture
def cliente_admin(aplicacion: FastAPI, administrador: Usuario) -> TestClient:
    """Cliente HTTP autenticado como administrador."""
    return TestClient(aplicacion, headers=cabecera_de(administrador))


@pytest.fixture
def cliente_anonimo(aplicacion: FastAPI) -> TestClient:
    """Cliente HTTP sin token."""
    return TestClient(aplicacion)
