"""Consultas de Usuario."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.usuario import Usuario
from app.data.repositories.base_repository import BaseRepository


class UsuarioRepository(BaseRepository[Usuario]):
    """Acceso a los usuarios."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Usuario)

    def buscar_por_correo(self, correo: str) -> Usuario | None:
        return self.sesion.scalars(select(Usuario).where(Usuario.correo == correo)).first()

    def buscar_por_google_id(self, google_id: str) -> Usuario | None:
        return self.sesion.scalars(select(Usuario).where(Usuario.google_id == google_id)).first()
