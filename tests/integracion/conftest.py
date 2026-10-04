"""Un PostgreSQL de verdad, levantado en Docker, para las pruebas de integración.

Las pruebas de `tests/` corren contra SQLite en memoria: son rápidas y no
necesitan infraestructura, y para probar reglas de negocio alcanza. Lo que no
prueban es **la base**. SQLite guarda `NUMERIC` como punto flotante, ignora el
largo declarado de un `VARCHAR`, y no aplica `ON DELETE CASCADE` salvo que se
encienda un `PRAGMA` que la fixture de `tests/conftest.py` no enciende.

Todo eso son diferencias que solo aparecen en producción. Ya pasó una vez: un
`StringDataRightTruncation` al vincular Outlook (commit `32deefc`) que la suite
en verde no vio, porque SQLite aceptaba felizmente un token más largo que su
columna.

**El esquema lo crean las migraciones de Flyway, no el mapeo.** La fixture
aplica `V1` a `V8` sobre el contenedor, en orden, igual que lo haría
`flyway migrate`. Hasta el Laboratorio 4 se usaba `Base.metadata.create_all()`,
y eso hacía que estas pruebas validaran el mapeo contra un esquema que el
propio mapeo había creado -por construcción, siempre coincidían-. Ahora corren
contra el esquema real: con sus `CHECK`, sus llaves foráneas compuestas, sus
tipos enumerados y sus *triggers*. Si el mapeo y las migraciones se separan,
acá es donde se nota.

El contenedor se levanta **una vez por sesión** de pytest -arrancar PostgreSQL
cuesta segundos, no milisegundos- y cada prueba corre dentro de su propia
transacción, que se revierte al terminar. Así las pruebas no se ven entre sí
sin pagar el precio de recrear el esquema en cada una.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.business.seguridad.contrasenas import hashear_contrasena
from app.business.services.usuario_service import UsuarioService
from app.config.database import obtener_sesion
from app.data.models.enums import RolUsuario
from app.data.models.usuario import Usuario
from app.data.repositories.usuario_repository import UsuarioRepository
from app.main import crear_app
from app.presentation.dependencies import (
    obtener_servicio_de_bitacora,
    obtener_servicio_de_tipo_cambio,
    obtener_servicio_de_usuarios,
)
from tests.conftest import COSTO_DE_HASH_EN_PRUEBAS, _bitacora_sin_mongo, cabecera_de

# `testcontainers` es una dependencia de desarrollo opcional: si no está
# instalada, estas pruebas se saltan en vez de romper la colección entera.
testcontainers_postgres = pytest.importorskip(
    "testcontainers.community.postgres",
    reason="testcontainers no está instalado (pip install -e '.[dev]')",
)

pytestmark = pytest.mark.integracion

DIRECTORIO_DE_MIGRACIONES = Path(__file__).resolve().parents[2] / "db" / "postgres" / "migrations"
CONTRASENA_DE_PRUEBA = "una-clave-larga"


def migraciones_en_orden() -> list[Path]:
    """Los archivos `V<n>__*.sql`, por número de versión.

    Por número y no por nombre: ordenadas como texto, `V10` iría antes que `V2`.
    """
    return sorted(
        DIRECTORIO_DE_MIGRACIONES.glob("V*__*.sql"),
        key=lambda archivo: int(archivo.name[1:].split("__")[0]),
    )


def aplicar_migraciones(motor: Engine) -> None:
    """Corre cada migración contra la base, en orden, y confirma.

    Va por la conexión cruda del driver y sin parámetros a propósito: así
    psycopg manda el archivo completo -varias sentencias, con sus funciones
    entre `$$`- tal como está escrito, que es lo que hace Flyway.
    """
    conexion = motor.raw_connection()
    try:
        with conexion.cursor() as cursor:
            for archivo in migraciones_en_orden():
                cursor.execute(archivo.read_text(encoding="utf-8"))
        conexion.commit()
    finally:
        conexion.close()


@pytest.fixture(scope="session")
def motor_postgres() -> Iterator[Engine]:
    """Un PostgreSQL 16 en Docker con el esquema de Flyway (`V1`…`V8`) aplicado.

    Se salta -no falla- si no hay un Docker con el que hablar: que alguien
    corra la suite sin Docker en su máquina no debería verse como un error del
    proyecto. En el CI sí hay, y ahí estas pruebas corren de verdad.
    """
    try:
        contenedor = testcontainers_postgres.PostgresContainer(
            "postgres:16-alpine",
            # El proyecto usa psycopg 3 (`postgresql+psycopg://`), no el
            # psycopg2 que testcontainers pone por defecto.
            driver="psycopg",
        )
        contenedor.start()
    except Exception as error:  # noqa: BLE001 -cualquier fallo de Docker es un skip
        pytest.skip(f"No se pudo levantar el PostgreSQL de prueba: {error}")

    try:
        motor = create_engine(contenedor.get_connection_url())
        aplicar_migraciones(motor)
        yield motor
        motor.dispose()
    finally:
        contenedor.stop()


@pytest.fixture
def sesion_postgres(motor_postgres: Engine) -> Iterator[Session]:
    """Sesión sobre el PostgreSQL real, dentro de una transacción que se revierte.

    La conexión abre una transacción externa que la prueba nunca confirma: al
    terminar se hace `rollback` y la base queda como estaba, aunque la prueba
    haya hecho `commit` por dentro (queda anidado en la externa). Es lo que
    permite compartir un solo contenedor entre todas las pruebas sin que una
    le deje datos a la siguiente.
    """
    conexion = motor_postgres.connect()
    transaccion = conexion.begin()
    fabrica = sessionmaker(bind=conexion, autoflush=False, expire_on_commit=False)
    sesion = fabrica()
    try:
        yield sesion
    finally:
        sesion.close()
        # `is_active` porque una prueba que provoca un error de integridad a
        # propósito deja la transacción ya abortada por PostgreSQL: intentar
        # revertirla otra vez solo produce un aviso.
        if transaccion.is_active:
            transaccion.rollback()
        conexion.close()


# ---- la API contra PostgreSQL ----


@pytest.fixture
def sesion_de_la_api(motor_postgres: Engine) -> Iterator[Session]:
    """Como `sesion_postgres`, pero para servicios que confirman y revierten por su cuenta.

    `join_transaction_mode="create_savepoint"` hace que cada `commit` y cada
    `rollback` de un servicio actúe sobre un *savepoint* dentro de la
    transacción externa de la prueba. Sin eso, el `rollback` que hace
    `ConciliacionService` cuando una escritura falla se llevaría también los
    datos que la prueba preparó.
    """
    conexion = motor_postgres.connect()
    transaccion = conexion.begin()
    sesion = Session(
        bind=conexion,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield sesion
    finally:
        sesion.close()
        if transaccion.is_active:
            transaccion.rollback()
        conexion.close()


@pytest.fixture
def aplicacion_postgres(sesion_de_la_api: Session) -> Iterator[FastAPI]:
    """La app real sobre el PostgreSQL de Flyway, sin Mongo ni red."""
    app = crear_app()
    app.dependency_overrides[obtener_sesion] = lambda: sesion_de_la_api
    app.dependency_overrides[obtener_servicio_de_bitacora] = _bitacora_sin_mongo
    app.dependency_overrides[obtener_servicio_de_tipo_cambio] = lambda: None
    app.dependency_overrides[obtener_servicio_de_usuarios] = lambda: UsuarioService(
        UsuarioRepository(sesion_de_la_api), costo_del_hash=COSTO_DE_HASH_EN_PRUEBAS
    )
    yield app
    app.dependency_overrides.clear()


def _cuenta(sesion: Session, correo: str, rol: RolUsuario) -> Usuario:
    """Una cuenta guardada con un hash de bcrypt real: el esquema exige uno."""
    usuario = Usuario(
        nombre_completo=f"Cuenta {rol.value.lower()}",
        correo=correo,
        contrasena_hash=hashear_contrasena(CONTRASENA_DE_PRUEBA, COSTO_DE_HASH_EN_PRUEBAS),
        rol=rol,
    )
    sesion.add(usuario)
    sesion.commit()
    return usuario


@pytest.fixture
def titular(sesion_de_la_api: Session) -> Usuario:
    return _cuenta(sesion_de_la_api, "titular@gastonomo.cr", RolUsuario.TITULAR)


@pytest.fixture
def otro_titular(sesion_de_la_api: Session) -> Usuario:
    return _cuenta(sesion_de_la_api, "otra@gastonomo.cr", RolUsuario.TITULAR)


@pytest.fixture
def administrador(sesion_de_la_api: Session) -> Usuario:
    return _cuenta(sesion_de_la_api, "admin@gastonomo.cr", RolUsuario.ADMIN)


@pytest.fixture
def api(aplicacion_postgres: FastAPI, titular: Usuario) -> TestClient:
    """Cliente autenticado como titular."""
    return TestClient(aplicacion_postgres, headers=cabecera_de(titular))


@pytest.fixture
def api_de_otro(aplicacion_postgres: FastAPI, otro_titular: Usuario) -> TestClient:
    """Cliente autenticado como un segundo titular."""
    return TestClient(aplicacion_postgres, headers=cabecera_de(otro_titular))


@pytest.fixture
def api_admin(aplicacion_postgres: FastAPI, administrador: Usuario) -> TestClient:
    """Cliente autenticado como administrador."""
    return TestClient(aplicacion_postgres, headers=cabecera_de(administrador))


@pytest.fixture
def api_anonima(aplicacion_postgres: FastAPI) -> TestClient:
    """Cliente sin token."""
    return TestClient(aplicacion_postgres)
