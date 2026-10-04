"""Reglas de negocio de las cuentas: registro y consulta.

`Usuario` es la raíz de aislamiento del sistema, así que este es el servicio
donde la verificación de propiedad del recurso (OWASP API1, *Broken Object
Level Authorization*) es más literal: `obtener` recibe **quién pide** además
de **qué pide**, y decide acá -no en el router- si le corresponde.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from app.business.errors import (
    AccesoDenegado,
    CorreoYaRegistrado,
    DatosInvalidos,
    RecursoNoEncontrado,
)
from app.business.seguridad.contrasenas import COSTO_POR_DEFECTO, hashear_contrasena
from app.business.services.auth_service import UsuarioAutenticado
from app.business.services.categoria_service import CategoriaService
from app.data.models.enums import Moneda, RolUsuario
from app.data.models.usuario import Usuario
from app.data.repositories.usuario_repository import UsuarioRepository

LARGO_MINIMO_CONTRASENA = 8
LARGO_MAXIMO_NOMBRE = 120
# El mismo formato que exige el CHECK `ck_usuario_correo_formato` de la base:
# validar acá lo que la base va a rechazar igual evita un error de integridad
# crudo donde corresponde un mensaje.
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


@dataclass(frozen=True)
class RegistrarUsuarioComando:
    """Lo que llega del formulario de registro."""

    nombre_completo: str
    correo: str
    contrasena: str


@dataclass(frozen=True)
class UsuarioDetalle:
    """Una cuenta tal como sale del negocio: sin el hash de su contraseña."""

    id: int
    nombre_completo: str
    correo: str
    moneda_preferida: Moneda
    rol: RolUsuario
    activo: bool
    creado_en: datetime


class UsuarioService:
    """Aplica las reglas del dominio sobre las cuentas."""

    def __init__(
        self,
        usuario_repository: UsuarioRepository,
        categoria_service: CategoriaService | None = None,
        costo_del_hash: int = COSTO_POR_DEFECTO,
    ) -> None:
        self.usuarios = usuario_repository
        # Opcional: sin él la cuenta se crea igual, solo que sin el catálogo
        # semilla de categorías.
        self.categoria_service = categoria_service
        self._costo_del_hash = costo_del_hash

    def registrar(self, comando: RegistrarUsuarioComando) -> UsuarioDetalle:
        """Crea una cuenta nueva.

        Reglas que aplica:

        - El nombre no puede venir vacío.
        - El correo tiene que tener forma de correo, y se guarda en minúsculas:
          `Ana@x.cr` y `ana@x.cr` son la misma persona.
        - La contraseña tiene al menos 8 caracteres. Nunca se guarda: se
          guarda su hash.
        - No puede haber dos cuentas con el mismo correo.
        - **Toda cuenta nace `TITULAR`.** El rol no se puede pedir al
          registrarse: si se pudiera, cualquiera se registraría como
          administrador.
        - La cuenta arranca con la jerarquía estándar de categorías, para que
          nadie empiece con una lista vacía.
        """
        nombre_completo = comando.nombre_completo.strip()
        correo = comando.correo.strip().lower()

        if not nombre_completo:
            raise DatosInvalidos("El nombre no puede venir vacío.")
        if len(nombre_completo) > LARGO_MAXIMO_NOMBRE:
            raise DatosInvalidos(f"El nombre no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres.")
        if not _PATRON_CORREO.match(correo):
            raise DatosInvalidos("El correo no es válido.")
        if len(comando.contrasena) < LARGO_MINIMO_CONTRASENA:
            raise DatosInvalidos(
                f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENA} caracteres."
            )
        if self.usuarios.buscar_por_correo(correo) is not None:
            raise CorreoYaRegistrado(f"Ya existe una cuenta con el correo {correo}.")

        usuario = Usuario(
            nombre_completo=nombre_completo,
            correo=correo,
            contrasena_hash=hashear_contrasena(comando.contrasena, self._costo_del_hash),
            rol=RolUsuario.TITULAR,
        )
        self.usuarios.agregar(usuario)
        self.usuarios.sesion.commit()
        if self.categoria_service is not None:
            self.categoria_service.sembrar_estandar(usuario.id)
        return _detalle(usuario)

    def obtener(self, solicitante: UsuarioAutenticado, usuario_id: int) -> UsuarioDetalle:
        """Los datos de una cuenta, solo para su dueño o para un administrador.

        La verificación de propiedad vive acá y no en el router: es una regla
        del dominio -«una cuenta solo la ve su dueño»-, y tiene que cumplirse
        igual si mañana este servicio se llama desde otro punto de entrada.

        Se verifica **antes** de buscar la cuenta. Al revés, un titular podría
        distinguir un 404 de un 403 y enumerar qué ids existen.
        """
        if solicitante.id != usuario_id and not solicitante.es_admin:
            raise AccesoDenegado("Solo podés consultar tu propia cuenta.")
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        return _detalle(usuario)

    def listar(self) -> list[UsuarioDetalle]:
        """Todas las cuentas. Quién puede pedirlo lo decide el rol, en la presentación."""
        return [_detalle(usuario) for usuario in self.usuarios.listar_por_correo()]


def _detalle(usuario: Usuario) -> UsuarioDetalle:
    return UsuarioDetalle(
        id=usuario.id,
        nombre_completo=usuario.nombre_completo,
        correo=usuario.correo,
        moneda_preferida=usuario.moneda_preferida,
        rol=usuario.rol,
        activo=usuario.activo,
        creado_en=usuario.creado_en,
    )
