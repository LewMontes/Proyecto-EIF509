"""Reglas de negocio de los métodos de pago de un titular.

Un `MetodoPago` nunca se crea automáticamente desde la ingesta -ver la nota
en el modelo. El titular lo registra a mano acá, y de ahí en adelante
`ConciliacionService` lo usa para emparejar por los últimos cuatro dígitos.
"""

from dataclasses import dataclass

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.data.models.enums import Moneda, TipoMetodoPago
from app.data.models.metodo_pago import MetodoPago
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.usuario_repository import UsuarioRepository

LARGO_MAXIMO_ALIAS = 60
TIPOS_CON_ULTIMOS_CUATRO = (TipoMetodoPago.DEBITO, TipoMetodoPago.CREDITO)


@dataclass(frozen=True)
class CrearMetodoPagoComando:
    """Orden que recibe el negocio para crear un método de pago."""

    usuario_id: int
    alias: str
    tipo: TipoMetodoPago
    moneda: Moneda = Moneda.CRC
    ultimos_cuatro: str | None = None
    entidad: str | None = None
    dia_corte: int | None = None


class MetodoPagoService:
    """Aplica las reglas del dominio sobre los métodos de pago de un titular."""

    def __init__(
        self,
        metodo_pago_repository: MetodoPagoRepository,
        usuario_repository: UsuarioRepository,
    ) -> None:
        self.metodos_pago = metodo_pago_repository
        self.usuarios = usuario_repository

    def crear(self, comando: CrearMetodoPagoComando) -> MetodoPago:
        """Crea un método de pago.

        Reglas que aplica:
        - El alias no puede venir vacío ni repetirse dentro de la cuenta.
        - Solo débito y crédito llevan últimos cuatro dígitos -el efectivo con
          un "0000" inventado ensuciaría el emparejamiento de la ingesta.
        - Si los llevan, tienen que ser exactamente 4 dígitos, y no pueden
          repetirse con otra tarjeta ya registrada de este mismo titular
          -si tuviera dos terminadas en 6411, el emparejamiento sería ambiguo.
        - El día de corte solo tiene sentido en una tarjeta de crédito.
        """
        alias = comando.alias.strip()
        if not alias:
            raise DatosInvalidos("El alias no puede venir vacío.")
        if len(alias) > LARGO_MAXIMO_ALIAS:
            raise DatosInvalidos(f"El alias no puede pasar de {LARGO_MAXIMO_ALIAS} caracteres.")

        self._asegurar_usuario_activo(comando.usuario_id)

        if self.metodos_pago.buscar_por_alias(comando.usuario_id, alias) is not None:
            raise ReglaDeNegocioViolada(f"Ya existe un método de pago llamado '{alias}'.")

        ultimos_cuatro = comando.ultimos_cuatro.strip() if comando.ultimos_cuatro else None
        if ultimos_cuatro:
            if comando.tipo not in TIPOS_CON_ULTIMOS_CUATRO:
                raise ReglaDeNegocioViolada("Solo débito y crédito llevan últimos cuatro dígitos.")
            if not (len(ultimos_cuatro) == 4 and ultimos_cuatro.isdigit()):
                raise DatosInvalidos("Los últimos cuatro dígitos deben ser 4 números.")
            if (
                self.metodos_pago.buscar_por_ultimos_cuatro(comando.usuario_id, ultimos_cuatro)
                is not None
            ):
                raise ReglaDeNegocioViolada(
                    f"Ya tenés otro método de pago terminado en {ultimos_cuatro}: el "
                    "emparejamiento de la ingesta sería ambiguo."
                )

        dia_corte = comando.dia_corte
        if dia_corte is not None:
            if comando.tipo != TipoMetodoPago.CREDITO:
                raise ReglaDeNegocioViolada("El día de corte solo aplica a una tarjeta de crédito.")
            if not (1 <= dia_corte <= 31):
                raise DatosInvalidos("El día de corte debe estar entre 1 y 31.")

        metodo_pago = MetodoPago(
            usuario_id=comando.usuario_id,
            alias=alias,
            tipo=comando.tipo,
            moneda=comando.moneda,
            ultimos_cuatro=ultimos_cuatro,
            entidad=comando.entidad.strip() if comando.entidad else None,
            dia_corte=dia_corte,
            activo=True,
        )
        self.metodos_pago.agregar(metodo_pago)
        self.metodos_pago.sesion.commit()
        return metodo_pago

    def listar(self, usuario_id: int) -> list[MetodoPago]:
        self._asegurar_usuario_activo(usuario_id)
        return self.metodos_pago.listar_de_usuario(usuario_id)

    def desactivar(self, usuario_id: int, metodo_pago_id: int) -> MetodoPago:
        """Desactiva un método de pago -nunca se borra: un gasto histórico tiene
        que poder seguir mostrando con qué tarjeta se pagó."""
        metodo_pago = self._obtener_del_titular(usuario_id, metodo_pago_id)
        metodo_pago.activo = False
        self.metodos_pago.sesion.commit()
        return metodo_pago

    def _obtener_del_titular(self, usuario_id: int, metodo_pago_id: int) -> MetodoPago:
        self._asegurar_usuario_activo(usuario_id)
        metodo_pago = self.metodos_pago.obtener_de_usuario(metodo_pago_id, usuario_id)
        if metodo_pago is None:
            raise RecursoNoEncontrado(
                f"El método de pago {metodo_pago_id} no existe en esta cuenta."
            )
        return metodo_pago

    def _asegurar_usuario_activo(self, usuario_id: int) -> None:
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        if not usuario.activo:
            raise ReglaDeNegocioViolada(f"El usuario {usuario_id} esta desactivado.")
