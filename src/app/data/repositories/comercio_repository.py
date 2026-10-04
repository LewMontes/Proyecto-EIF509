"""Consultas de Comercio."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.comercio import Comercio
from app.data.paginacion import Pagina, SolicitudDePagina, paginar
from app.data.repositories.base_repository import BaseRepository


class ComercioRepository(BaseRepository[Comercio]):
    """Acceso al catálogo compartido de comercios."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Comercio)

    def buscar_por_nombre_normalizado(self, nombre_normalizado: str) -> Comercio | None:
        return self.sesion.scalars(
            select(Comercio).where(Comercio.nombre_normalizado == nombre_normalizado)
        ).first()

    COLUMNAS_ORDENABLES = {"nombre": Comercio.nombre_normalizado, "id": Comercio.id}

    def buscar(self, nombre_contiene: str | None, solicitud: SolicitudDePagina) -> Pagina[Comercio]:
        """Una página del catálogo, opcionalmente solo los que contienen ese texto.

        Se compara contra `nombre_normalizado` -mayúsculas, sin acentos-, así
        que quien llama tiene que pasar el texto ya normalizado.
        """
        consulta = select(Comercio)
        if nombre_contiene:
            consulta = consulta.where(Comercio.nombre_normalizado.contains(nombre_contiene))
        return paginar(
            self.sesion, consulta, solicitud, self.COLUMNAS_ORDENABLES, desempate=Comercio.id
        )
