"""Conexion a la base de datos.

El motor se crea de forma perezosa, la primera vez que alguien lo pide, para que
importar la aplicacion no obligue a tener la base levantada.
"""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def crear_tablas() -> None:
    """Crea las tablas que falten a partir de los modelos.

    Sirve para el Laboratorio 1. Mas adelante lo sustituye una herramienta de
    migraciones, que versiona cada cambio del esquema en el repositorio en vez
    de deducirlo de los modelos.
    """
    from app.data.models import Base  # importa todos los modelos y llena el metadata

    Base.metadata.create_all(bind=get_engine())


def get_session() -> Iterator[Session]:
    """Dependencia de FastAPI: abre una sesion por request y la cierra al terminar."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
