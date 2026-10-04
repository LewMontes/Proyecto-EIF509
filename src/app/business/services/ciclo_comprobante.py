"""El ciclo de vida de un comprobante, como patrón State.

Un comprobante pasa por cinco estados (ver «Proceso 2» en
docs/propuesta-dominio.md):

    RECIBIDO --parsear--> PARSEADO --procesar--> PROCESADO
        |                    |
        |                    +-- dejar_pendiente / registrar_fallo (1.o y 2.o): sigue PARSEADO
        |                    +-- registrar_fallo (3.o) --> FALLIDO
        +--parsear (confianza baja)--> REVISION_MANUAL

Lo que se le puede pedir a un comprobante depende de en qué estado está: uno
`RECIBIDO` se puede parsear pero no procesar; uno `PROCESADO` ya originó su
compra y no admite nada más. Escrito con condicionales, cada operación de la
ingesta empezaría con su propio `if comprobante.estado in (...)`, y agregar un
estado obligaría a revisar todos.

Con State, **cada estado es una clase que sabe qué transiciones admite**. La
clase base rechaza todas; cada estado concreto sobrescribe solo las suyas. La
ingesta no pregunta en qué estado está el comprobante: le pide la operación al
estado, y el estado la hace o lanza `TransicionDeComprobanteInvalida`.
"""

from app.business.errors import TransicionDeComprobanteInvalida
from app.data.models.comprobante import Comprobante
from app.data.models.enums import EstadoComprobante

# La propuesta de dominio: «un comprobante que falla tres veces pasa a FALLIDO».
MAXIMO_DE_INTENTOS = 3
# Y: «por debajo de 0.75 de confianza, el comprobante no se convierte en compra solo».
CONFIANZA_MINIMA = 0.75


class EstadoDelComprobante:
    """Un estado del ciclo. Por defecto no admite ninguna transición."""

    nombre: EstadoComprobante

    def __init__(self, comprobante: Comprobante) -> None:
        self.comprobante = comprobante

    @property
    def admite_conciliacion(self) -> bool:
        """Si desde este estado tiene sentido intentar convertirlo en compra."""
        return False

    def asegurar_conciliable(self) -> None:
        """Corta la conciliación si el comprobante no está en un estado que la admita.

        Es lo que hace idempotente a la ingesta desde el lado del negocio: un
        comprobante `PROCESADO` que se intenta conciliar otra vez no duplica el
        gasto, se rechaza.
        """
        if not self.admite_conciliacion:
            self._rechazar("conciliar")

    def parsear(self, confianza: float, es_conciliable: bool, motivo: str | None = None) -> None:
        """Registra el resultado de leer el mensaje."""
        self._rechazar("parsear")

    def procesar(self, compra_id: int) -> None:
        """Lo liga a la compra que originó."""
        self._rechazar("procesar")

    def dejar_pendiente(self, motivo: str) -> None:
        """No se pudo conciliar todavía por algo que no es un fallo (falta la tasa del día)."""
        self._rechazar("dejar pendiente")

    def registrar_fallo(self, motivo: str) -> None:
        """La conciliación reventó. Cuenta un intento."""
        self._rechazar("registrar un fallo en")

    def _rechazar(self, operacion: str) -> None:
        raise TransicionDeComprobanteInvalida(
            f"No se puede {operacion} un comprobante en estado {self.nombre.value}."
        )

    def _pasar_a(self, estado: EstadoComprobante) -> None:
        self.comprobante.estado = estado


class Recibido(EstadoDelComprobante):
    """Recién llegó: solo existe la constancia del mensaje."""

    nombre = EstadoComprobante.RECIBIDO

    def parsear(self, confianza: float, es_conciliable: bool, motivo: str | None = None) -> None:
        self.comprobante.confianza = confianza
        if es_conciliable and confianza >= CONFIANZA_MINIMA:
            self._pasar_a(EstadoComprobante.PARSEADO)
            return
        # Preferimos molestar al titular antes que meterle un gasto inventado.
        self.comprobante.motivo_fallo = motivo or (
            f"La confianza del parseo ({confianza:.2f}) no llega a {CONFIANZA_MINIMA}."
        )
        self._pasar_a(EstadoComprobante.REVISION_MANUAL)


class Parseado(EstadoDelComprobante):
    """Ya se leyó con confianza suficiente: es el único estado que se concilia."""

    nombre = EstadoComprobante.PARSEADO

    @property
    def admite_conciliacion(self) -> bool:
        return True

    def procesar(self, compra_id: int) -> None:
        self.comprobante.compra_id = compra_id
        self.comprobante.motivo_fallo = None
        self._pasar_a(EstadoComprobante.PROCESADO)

    def dejar_pendiente(self, motivo: str) -> None:
        # Se queda en PARSEADO y no cuenta como intento: que el Banco Central
        # todavía no publique la tasa de ese día no es un fallo del
        # comprobante, y contarlo lo mandaría a FALLIDO por esperar tres días.
        self.comprobante.motivo_fallo = motivo

    def registrar_fallo(self, motivo: str) -> None:
        self.comprobante.intentos_procesamiento += 1
        self.comprobante.motivo_fallo = motivo
        if self.comprobante.intentos_procesamiento >= MAXIMO_DE_INTENTOS:
            self._pasar_a(EstadoComprobante.FALLIDO)


class EnRevisionManual(EstadoDelComprobante):
    """La lectura no alcanzó para conciliar sola. Lo resuelve una persona."""

    nombre = EstadoComprobante.REVISION_MANUAL


class Procesado(EstadoDelComprobante):
    """Ya originó su compra. Terminal: es lo que hace idempotente la ingesta."""

    nombre = EstadoComprobante.PROCESADO


class Fallido(EstadoDelComprobante):
    """Falló tres veces. Terminal: no hay un cuarto intento."""

    nombre = EstadoComprobante.FALLIDO


_ESTADOS: dict[EstadoComprobante, type[EstadoDelComprobante]] = {
    estado.nombre: estado for estado in (Recibido, Parseado, EnRevisionManual, Procesado, Fallido)
}


def estado_de(comprobante: Comprobante) -> EstadoDelComprobante:
    """El objeto de estado que corresponde al estado guardado del comprobante."""
    return _ESTADOS[comprobante.estado](comprobante)
