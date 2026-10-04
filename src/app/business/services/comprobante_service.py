"""La ingesta de un comprobante: el punto de entrada del Proceso 2.

Hasta el Laboratorio 4, `ConciliacionService.conciliar` existía y estaba
probado, pero nada lo invocaba fuera de las pruebas. Este servicio es lo que lo
conecta con la aplicación: recibe lo que el lector extrajo de un mensaje, deja
la constancia de que ese mensaje llegó, y dispara la conciliación.

Hace los pasos 1-2 del proceso (ver docs/propuesta-dominio.md) y delega el
resto:

1. Valida que el buzón sea del titular y esté activo, y que el mensaje no se
   haya recibido antes -la ingesta es idempotente.
2. Guarda el `Comprobante` en `RECIBIDO` y **confirma**. Va en su propio commit
   a propósito: la constancia de que el mensaje llegó tiene que sobrevivir
   aunque la conciliación falle, porque es lo que permite reintentarla y contar
   sus intentos.
3. Llama a `ConciliacionService.conciliar` con un `ConciliarComprobanteComando`.

Nada de lo que entra o sale es una entidad: entra un
`RegistrarComprobanteComando` y sale un `ComprobanteDetalle`.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.business.errors import (
    ComprobanteDuplicado,
    CuentaCorreoInactiva,
    FechaFutura,
    MontoNoPositivo,
    RecursoNoEncontrado,
)
from app.business.services.ciclo_comprobante import estado_de
from app.business.services.conciliacion_service import (
    ConciliacionService,
    ConciliarComprobanteComando,
)
from app.data.models.comprobante import Comprobante
from app.data.models.enums import EstadoComprobante, EstadoCuentaCorreo
from app.data.repositories.comprobante_repository import ComprobanteRepository
from app.data.repositories.cuenta_correo_repository import CuentaCorreoRepository

_TIPO_COMPRA = "COMPRA"
# Los cuatro campos de los que sale la confianza del parseo (propuesta de dominio).
_CAMPOS_OBLIGATORIOS = ("comercio", "fecha", "ultimos_cuatro", "monto")


@dataclass(frozen=True)
class RegistrarComprobanteComando:
    """Orden que recibe el negocio cuando llega la notificación de un banco.

    Trae los campos ya extraídos del mensaje -nunca su cuerpo, que el sistema
    no almacena-. `confianza` es la que calculó el lector; si no viene, se
    deriva de cuántos de los cuatro campos obligatorios llegaron.
    """

    usuario_id: int
    cuenta_correo_id: int
    mensaje_id: str
    remitente: str
    banco: str
    comercio: str | None
    monto: Decimal | None
    moneda: str | None
    fecha: datetime | None
    ultimos_cuatro: str | None = None
    tipo_transaccion: str = _TIPO_COMPRA
    confianza: float | None = None
    recibido_en: datetime | None = None


@dataclass(frozen=True)
class ComprobanteDetalle:
    """Un comprobante tal como sale del negocio."""

    id: int
    cuenta_correo_id: int
    mensaje_id: str
    remitente: str
    recibido_en: datetime
    estado: EstadoComprobante
    banco: str
    comercio: str | None
    monto: Decimal | None
    moneda: str | None
    fecha: datetime | None
    ultimos_cuatro: str | None
    tipo_transaccion: str | None
    confianza: float
    intentos_procesamiento: int
    motivo_fallo: str | None
    compra_id: int | None


class ComprobanteService:
    """Recibe comprobantes y los pasa por la conciliación."""

    def __init__(
        self,
        comprobante_repository: ComprobanteRepository,
        cuenta_correo_repository: CuentaCorreoRepository,
        conciliacion: ConciliacionService,
    ) -> None:
        self.comprobantes = comprobante_repository
        self.cuentas = cuenta_correo_repository
        self.conciliacion = conciliacion

    def registrar(self, comando: RegistrarComprobanteComando) -> ComprobanteDetalle:
        """Recibe un comprobante y lo concilia.

        Reglas y validaciones que aplica:

        - El buzón tiene que existir, **ser del titular** y estar activo.
        - El monto extraído, si vino, tiene que ser mayor que cero.
        - La fecha extraída, si vino, no puede ser futura.
        - El mismo mensaje del mismo buzón no se recibe dos veces.

        El comprobante se guarda aunque después no se pueda conciliar: queda en
        `REVISION_MANUAL` (confianza baja o campos faltantes) o pendiente en
        `PARSEADO` (falta el tipo de cambio de su fecha), y `estado` y
        `motivo_fallo` lo dicen.
        """
        cuenta = self.cuentas.obtener_de_usuario(comando.cuenta_correo_id, comando.usuario_id)
        if cuenta is None:
            raise RecursoNoEncontrado(
                f"El buzón {comando.cuenta_correo_id} no existe en esta cuenta."
            )
        if cuenta.estado != EstadoCuentaCorreo.ACTIVA:
            raise CuentaCorreoInactiva(
                f"El buzón {cuenta.direccion} está {cuenta.estado.value}: no recibe comprobantes."
            )
        if comando.monto is not None and comando.monto <= 0:
            raise MontoNoPositivo("El monto del comprobante debe ser mayor que cero.")
        if comando.fecha is not None and comando.fecha > datetime.now():
            raise FechaFutura("La fecha del comprobante no puede ser futura.")

        mensaje_id = comando.mensaje_id.strip()
        if self.comprobantes.buscar_por_mensaje(cuenta.id, mensaje_id) is not None:
            raise ComprobanteDuplicado(
                f"El mensaje {mensaje_id} de ese buzón ya se había recibido: no se duplica."
            )

        confianza = comando.confianza if comando.confianza is not None else _confianza_de(comando)
        comprobante = Comprobante(
            usuario_id=comando.usuario_id,
            cuenta_correo_id=cuenta.id,
            mensaje_id=mensaje_id,
            remitente=comando.remitente.strip(),
            recibido_en=comando.recibido_en or datetime.now(UTC),
            estado=EstadoComprobante.RECIBIDO,
            banco=comando.banco.strip(),
            comercio=comando.comercio.strip() if comando.comercio else None,
            fecha=comando.fecha,
            ultimos_cuatro=comando.ultimos_cuatro,
            tipo_transaccion=comando.tipo_transaccion,
            moneda=comando.moneda,
            monto=comando.monto,
            confianza=confianza,
        )
        self.comprobantes.agregar(comprobante)
        # La constancia se confirma antes de conciliar -ver el docstring del módulo.
        self.comprobantes.sesion.commit()

        self.conciliacion.conciliar(_comando_de_conciliacion(comprobante))
        return _detalle(comprobante)

    def reintentar(self, usuario_id: int, comprobante_id: int) -> ComprobanteDetalle:
        """Vuelve a intentar la conciliación de un comprobante que quedó pendiente.

        Sirve para los dos casos que dejan un comprobante en `PARSEADO`: el que
        esperaba el tipo de cambio de su fecha, y el que falló una o dos veces.
        Cualquier otro estado se rechaza -`PROCESADO` ya tiene su compra,
        `FALLIDO` agotó sus tres intentos, `REVISION_MANUAL` lo resuelve una
        persona-: quien decide es el estado, no este método.
        """
        comprobante = self._del_titular(usuario_id, comprobante_id)
        estado_de(comprobante).asegurar_conciliable()
        self.conciliacion.conciliar(_comando_de_conciliacion(comprobante))
        return _detalle(comprobante)

    def obtener(self, usuario_id: int, comprobante_id: int) -> ComprobanteDetalle:
        """El comprobante, solo si pertenece al titular que lo pide."""
        return _detalle(self._del_titular(usuario_id, comprobante_id))

    def listar(
        self, usuario_id: int, estado: EstadoComprobante | None = None
    ) -> list[ComprobanteDetalle]:
        """Los comprobantes del titular, del más reciente al más viejo."""
        return [
            _detalle(comprobante)
            for comprobante in self.comprobantes.listar_de_usuario(usuario_id, estado)
        ]

    def _del_titular(self, usuario_id: int, comprobante_id: int) -> Comprobante:
        comprobante = self.comprobantes.obtener_de_usuario(comprobante_id, usuario_id)
        if comprobante is None:
            raise RecursoNoEncontrado(f"El comprobante {comprobante_id} no existe en esta cuenta.")
        return comprobante


def _confianza_de(comando: RegistrarComprobanteComando) -> float:
    """Proporción de los cuatro campos obligatorios que el lector logró extraer."""
    encontrados = sum(1 for campo in _CAMPOS_OBLIGATORIOS if getattr(comando, campo) is not None)
    return encontrados / len(_CAMPOS_OBLIGATORIOS)


def _comando_de_conciliacion(comprobante: Comprobante) -> ConciliarComprobanteComando:
    return ConciliarComprobanteComando(
        usuario_id=comprobante.usuario_id,
        comprobante_id=comprobante.id,
        comercio=comprobante.comercio,
        monto=comprobante.monto,
        moneda=comprobante.moneda,
        fecha=comprobante.fecha,
        ultimos_cuatro=comprobante.ultimos_cuatro,
        tipo_transaccion=comprobante.tipo_transaccion,
        confianza=float(comprobante.confianza),
    )


def _detalle(comprobante: Comprobante) -> ComprobanteDetalle:
    return ComprobanteDetalle(
        id=comprobante.id,
        cuenta_correo_id=comprobante.cuenta_correo_id,
        mensaje_id=comprobante.mensaje_id,
        remitente=comprobante.remitente,
        recibido_en=comprobante.recibido_en,
        estado=comprobante.estado,
        banco=comprobante.banco,
        comercio=comprobante.comercio,
        monto=comprobante.monto,
        moneda=comprobante.moneda,
        fecha=comprobante.fecha,
        ultimos_cuatro=comprobante.ultimos_cuatro,
        tipo_transaccion=comprobante.tipo_transaccion,
        confianza=float(comprobante.confianza),
        intentos_procesamiento=comprobante.intentos_procesamiento,
        motivo_fallo=comprobante.motivo_fallo,
        compra_id=comprobante.compra_id,
    )
