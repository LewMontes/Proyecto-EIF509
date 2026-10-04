"""Reglas de negocio de los buzones del titular.

Un `Comprobante` siempre pertenece a un buzón -es lo que hace idempotente la
ingesta: el identificador del mensaje es único **dentro de su buzón**-, así que
antes de recibir el primero tiene que existir la `CuentaCorreo` de la que
viene. Este servicio la registra.

Registrar el buzón no es enlazarlo con el proveedor: el intercambio OAuth2 con
Microsoft o Google, que es de donde salen los tokens, queda fuera de esta
entrega. Un buzón recién registrado nace sin tokens y `ACTIVA`.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from app.business.errors import (
    CuentaCorreoYaVinculada,
    DatosInvalidos,
    RecursoNoEncontrado,
    UsuarioInactivo,
)
from app.data.models.cuenta_correo import CuentaCorreo
from app.data.models.enums import EstadoCuentaCorreo, ProveedorCorreo
from app.data.repositories.cuenta_correo_repository import CuentaCorreoRepository
from app.data.repositories.usuario_repository import UsuarioRepository

_PATRON_DIRECCION = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


@dataclass(frozen=True)
class CuentaCorreoDetalle:
    """Un buzón tal como sale del negocio: sin ningún dato de token."""

    id: int
    proveedor: ProveedorCorreo
    direccion: str
    estado: EstadoCuentaCorreo
    ultima_sincronizacion: datetime | None


class CuentaCorreoService:
    """Aplica las reglas del dominio sobre los buzones de un titular."""

    def __init__(
        self,
        cuenta_correo_repository: CuentaCorreoRepository,
        usuario_repository: UsuarioRepository,
    ) -> None:
        self.cuentas = cuenta_correo_repository
        self.usuarios = usuario_repository

    def registrar(
        self, usuario_id: int, proveedor: ProveedorCorreo, direccion: str
    ) -> CuentaCorreoDetalle:
        """Registra un buzón del titular.

        Reglas que aplica:

        - El titular tiene que existir y estar activo.
        - La dirección tiene que tener forma de correo; se guarda en minúsculas.
        - Un titular no registra dos veces la misma dirección.
        """
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        if not usuario.activo:
            raise UsuarioInactivo(f"El usuario {usuario_id} esta desactivado.")

        direccion = direccion.strip().lower()
        if not _PATRON_DIRECCION.match(direccion):
            raise DatosInvalidos("La dirección del buzón no es un correo válido.")
        if self.cuentas.buscar_por_direccion(usuario_id, proveedor, direccion) is not None:
            raise CuentaCorreoYaVinculada(f"El buzón {direccion} ya está registrado en la cuenta.")

        cuenta = CuentaCorreo(
            usuario_id=usuario_id,
            proveedor=proveedor,
            direccion=direccion,
            estado=EstadoCuentaCorreo.ACTIVA,
        )
        self.cuentas.agregar(cuenta)
        self.cuentas.sesion.commit()
        return _detalle(cuenta)

    def listar(self, usuario_id: int) -> list[CuentaCorreoDetalle]:
        return [_detalle(cuenta) for cuenta in self.cuentas.listar_de_usuario(usuario_id)]

    def obtener(self, usuario_id: int, cuenta_correo_id: int) -> CuentaCorreoDetalle:
        """El buzón, solo si pertenece al titular que lo pide."""
        cuenta = self.cuentas.obtener_de_usuario(cuenta_correo_id, usuario_id)
        if cuenta is None:
            raise RecursoNoEncontrado(f"El buzón {cuenta_correo_id} no existe en esta cuenta.")
        return _detalle(cuenta)


def _detalle(cuenta: CuentaCorreo) -> CuentaCorreoDetalle:
    return CuentaCorreoDetalle(
        id=cuenta.id,
        proveedor=cuenta.proveedor,
        direccion=cuenta.direccion,
        estado=cuenta.estado,
        ultima_sincronizacion=cuenta.ultima_sincronizacion,
    )
