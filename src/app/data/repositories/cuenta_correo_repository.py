"""Consultas de CuentaCorreo.

Todas reciben `usuario_id` y filtran por él, igual que el repositorio de
categorías: el aislamiento entre cuentas se sostiene aquí.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.cuenta_correo import CuentaCorreo
from app.data.models.enums import ProveedorCorreo
from app.data.repositories.base_repository import BaseRepository


class CuentaCorreoRepository(BaseRepository[CuentaCorreo]):
    """Acceso a los buzones vinculados de un usuario."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, CuentaCorreo)

    def buscar_por_direccion(
        self, usuario_id: int, proveedor: ProveedorCorreo, direccion: str
    ) -> CuentaCorreo | None:
        """Busca si esa dirección ya está vinculada para ese titular.

        Vincular dos veces el mismo buzón no debe duplicar la fila: debe
        actualizar los tokens de la que ya existe.
        """
        return self.sesion.scalars(
            select(CuentaCorreo).where(
                CuentaCorreo.usuario_id == usuario_id,
                CuentaCorreo.proveedor == proveedor,
                CuentaCorreo.direccion == direccion,
            )
        ).first()

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> CuentaCorreo | None:
        """Obtiene una cuenta de correo solo si pertenece al titular indicado."""
        return self.sesion.scalars(
            select(CuentaCorreo).where(
                CuentaCorreo.id == identificador,
                CuentaCorreo.usuario_id == usuario_id,
            )
        ).first()

    def listar_de_usuario(self, usuario_id: int) -> list[CuentaCorreo]:
        return list(
            self.sesion.scalars(
                select(CuentaCorreo)
                .where(CuentaCorreo.usuario_id == usuario_id)
                .order_by(CuentaCorreo.direccion)
            )
        )
