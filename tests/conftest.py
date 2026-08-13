"""Piezas compartidas por las pruebas.

Las pruebas corren contra una base SQLite en memoria: se crea vacia para cada
prueba y desaparece al terminar. Asi la suite no depende de que haya un servidor
de base de datos levantado, ni en la maquina de nadie ni en la CI.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.database import get_session
from app.data.models import Base, Usuario
from app.main import crear_app


@pytest.fixture
def session() -> Iterator[Session]:
    """Sesion contra una base en memoria, nueva para cada prueba."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        # Sin StaticPool, cada conexion abriria su propia base en memoria vacia.
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)

    with fabrica() as sesion:
        yield sesion

    Base.metadata.drop_all(engine)


@pytest.fixture
def usuario(session: Session) -> Usuario:
    """Un usuario ya guardado, para colgarle categorias."""
    nuevo = Usuario(nombre_completo="Usuario de prueba", correo="prueba@est.una.ac.cr")
    session.add(nuevo)
    session.commit()
    return nuevo


@pytest.fixture
def cliente(session: Session) -> Iterator[TestClient]:
    """Cliente HTTP contra la app real, pero apuntando a la base en memoria."""
    app = crear_app()
    app.dependency_overrides[get_session] = lambda: session

    yield TestClient(app)

    app.dependency_overrides.clear()
