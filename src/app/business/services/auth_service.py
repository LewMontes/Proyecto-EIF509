"""Autenticación: canjear correo y contraseña por un token, y un token por una identidad.

Es *stateless*: no hay tabla de sesiones. `iniciar_sesion` firma un JWT y lo
entrega; de ahí en adelante cada petición trae ese token y `usuario_de_token`
lo convierte en la identidad de quien pide. Cerrar sesión es descartar el token
del lado del cliente.

Lo que sale de acá hacia la presentación es `UsuarioAutenticado`, no la entidad
`Usuario`: la identidad de una petición es un dato inmutable -quién es y qué
rol tiene-, no una fila que alguien pueda modificar por accidente.
"""

from dataclasses import dataclass

from app.business.errors import CredencialesInvalidas, NoAutenticado
from app.business.seguridad.contrasenas import verificar_contrasena
from app.business.seguridad.tokens import emitir_token, leer_token
from app.data.models.enums import RolUsuario
from app.data.repositories.usuario_repository import UsuarioRepository


@dataclass(frozen=True)
class IniciarSesionComando:
    """Lo que llega del formulario de login."""

    correo: str
    contrasena: str


@dataclass(frozen=True)
class UsuarioAutenticado:
    """La identidad detrás de una petición: quién es y qué rol tiene."""

    id: int
    correo: str
    nombre_completo: str
    rol: RolUsuario

    @property
    def es_admin(self) -> bool:
        return self.rol == RolUsuario.ADMIN


@dataclass(frozen=True)
class SesionIniciada:
    """Lo que se le devuelve al cliente al iniciar sesión."""

    access_token: str
    expira_en_segundos: int
    usuario: UsuarioAutenticado


class AuthService:
    """Aplica las reglas de autenticación."""

    def __init__(
        self, usuario_repository: UsuarioRepository, jwt_secreto: str, jwt_minutos: int
    ) -> None:
        self.usuarios = usuario_repository
        self._secreto = jwt_secreto
        self._minutos = jwt_minutos

    def iniciar_sesion(self, comando: IniciarSesionComando) -> SesionIniciada:
        """Verifica correo y contraseña y emite el token de acceso.

        El error es el mismo -y con el mismo mensaje- para un correo que no
        existe, una contraseña equivocada, una cuenta sin contraseña propia y
        una cuenta desactivada: distinguirlos le confirmaría a quien prueba
        correos cuáles sí tienen cuenta.
        """
        usuario = self.usuarios.buscar_por_correo(comando.correo.strip().lower())
        if (
            usuario is None
            or not usuario.activo
            or usuario.contrasena_hash is None
            or not verificar_contrasena(comando.contrasena, usuario.contrasena_hash)
        ):
            raise CredencialesInvalidas("Correo o contraseña incorrectos.")

        token = emitir_token(usuario.id, usuario.rol, self._secreto, self._minutos)
        return SesionIniciada(
            access_token=token.access_token,
            expira_en_segundos=token.expira_en_segundos,
            usuario=UsuarioAutenticado(
                id=usuario.id,
                correo=usuario.correo,
                nombre_completo=usuario.nombre_completo,
                rol=usuario.rol,
            ),
        )

    def usuario_de_token(self, token: str) -> UsuarioAutenticado:
        """La identidad detrás de un token, verificada contra la cuenta real.

        El token trae el rol, pero **el rol que vale es el de la base**: se
        relee la cuenta en cada petición. Así desactivar a alguien, o quitarle
        el rol de administrador, surte efecto de inmediato en vez de esperar a
        que su token venza. Es una consulta por llave primaria por petición, a
        cambio de no necesitar una lista de tokens revocados.
        """
        contenido = leer_token(token, self._secreto)
        usuario = self.usuarios.obtener_por_id(contenido.usuario_id)
        if usuario is None or not usuario.activo:
            raise NoAutenticado("La cuenta de este token ya no está disponible.")
        return UsuarioAutenticado(
            id=usuario.id,
            correo=usuario.correo,
            nombre_completo=usuario.nombre_completo,
            rol=usuario.rol,
        )
