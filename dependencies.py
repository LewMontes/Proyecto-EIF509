"""Armado de los servicios que usan los routers.

Es el unico punto donde la capa de presentacion decide COMO se construye un
servicio de negocio. Los routers piden el servicio ya listo y no saben que
detras hay un repositorio ni una sesion de base de datos.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.business.services.categoria_service import CategoriaService
from app.config.database import get_session
from app.data.repositories.categoria_repository import CategoriaRepository

SesionBD = Annotated[Session, Depends(get_session)]


def get_categoria_service(session: SesionBD) -> CategoriaService:
    return CategoriaService(CategoriaRepository(session))


ServicioCategoria = Annotated[CategoriaService, Depends(get_categoria_service)]
