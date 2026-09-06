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

El contenedor se levanta **una vez por sesión** de pytest -arrancar PostgreSQL
cuesta segundos, no milisegundos- y cada prueba corre dentro de su propia
transacción, que se revierte al terminar. Así las pruebas no se ven entre sí
sin pagar el precio de recrear el esquema en cada una.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.data.models import Base

# `testcontainers` es una dependencia de desarrollo opcional: si no está
# instalada, estas pruebas se saltan en vez de romper la colección entera.
testcontainers_postgres = pytest.importorskip(
    "testcontainers.community.postgres",
    reason="testcontainers no está instalado (pip install -e '.[dev]')",
)

pytestmark = pytest.mark.integracion


@pytest.fixture(scope="session")
def motor_postgres() -> Iterator[Engine]:
    """Un PostgreSQL 16 en Docker con el esquema de la aplicación ya creado.

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
        # El mismo `create_all` que usa la aplicación al arrancar: lo que se
        # prueba es el esquema que el mapeo produce, con los tipos reales de
        # PostgreSQL detrás.
        Base.metadata.create_all(bind=motor)
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
