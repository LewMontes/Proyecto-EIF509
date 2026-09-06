"""Piezas compartidas por las pruebas.

Las pruebas corren contra una base SQLite en memoria: se crea vacia para cada
prueba y desaparece al terminar. Asi la suite no depende de que haya un servidor
de base de datos levantado, ni en la maquina de nadie ni en la CI.

Lo que estas fixtures **no** prueban es la base misma -SQLite guarda `NUMERIC`
como punto flotante, ignora el largo de un `VARCHAR` y no aplica
`ON DELETE CASCADE`. Para eso estan las pruebas de `tests/integracion/`, que
levantan un PostgreSQL real con Testcontainers y traen sus propias fixtures.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.services.bitacora_service import BitacoraComprasService
from app.config.database import obtener_sesion
from app.data.models import Base, Usuario
from app.data.repositories.bitacora_repository import BitacoraRepository
from app.main import crear_app
from app.presentation.dependencies import obtener_servicio_de_bitacora


def _bitacora_sin_mongo() -> BitacoraComprasService:
    """Bitacora con un repositorio sin coleccion: cualquier llamado es un no-op."""
    return BitacoraComprasService(BitacoraRepository(None))


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
def cliente(sesion: Session) -> Iterator[TestClient]:
    """Cliente HTTP contra la app real, pero apuntando a la base en memoria.

    Tambien reemplaza el servicio de bitacora por uno sin coleccion real: sin
    este override, cualquier prueba que tocara `/api/compras/{id}/bitacora` se
    quedaria intentando conectar a un Mongo que no existe en la CI durante los
    3 segundos del timeout de `obtener_coleccion_bitacora` antes de fallar con
    gracia. Una prueba que si necesite verificar eventos reales pisa este mismo
    override con su propio doble.
    """
    app = crear_app()
    app.dependency_overrides[obtener_sesion] = lambda: sesion
    app.dependency_overrides[obtener_servicio_de_bitacora] = _bitacora_sin_mongo

    yield TestClient(app)

    app.dependency_overrides.clear()
