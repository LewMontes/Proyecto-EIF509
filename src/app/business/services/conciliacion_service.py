"""Conciliación transaccional de un comprobante en una Compra real de negocio.

Implementa los pasos 3-9 del Proceso 2 del dominio (ver
docs/propuesta-dominio.md): cerrar el parseo, emparejar método de pago,
resolver comercio, categorizar, crear la `Compra` y su línea, acumular el
presupuesto, y dejar el comprobante `PROCESADO` y ligado a su compra. Los pasos
1-2 -recibir el mensaje y guardar el `Comprobante` en `RECIBIDO`- los hace
`ComprobanteService.registrar` antes de llamar acá.

**Recibe una orden propia, no una entidad.** `conciliar` toma un
`ConciliarComprobanteComando` y devuelve un `ResultadoConciliacion`: ninguna
entidad del ORM entra ni sale de este servicio hacia la capa de presentación.

Todo lo que `conciliar` escribe en PostgreSQL -`Compra`, `LineaCompra`, el
contador de la regla que acertó, `Presupuesto.monto_consumido` y el estado y
`compra_id` del `Comprobante`- queda en una sola transacción: si algo falla a
mitad de camino, se revierte todo -nunca queda un comprobante marcado como
procesado sin que su gasto se haya sumado al presupuesto. La resolución del
`Comercio` (`ComercioService.resolver_o_crear`) confirma aparte, con su
propio commit: es un catálogo compartido entre titulares, y su creación no
es parte de la conciliación de uno en particular.

Lo único que se escribe **después** de un fallo, y a propósito fuera de la
transacción revertida, es el conteo del intento: tres fallos mandan el
comprobante a `FALLIDO` (ver `ciclo_comprobante.py`).

La bitácora de Mongo se escribe **después** de confirmar en PostgreSQL, y
nunca puede hacer fallar la conciliación -ver `BitacoraComprasService`.
"""

import contextlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.business.errors import (
    CategoriaNoEsHoja,
    CompraYaAnulada,
    CorreccionVacia,
    ErrorDeProveedorExterno,
    MetodoPagoInactivo,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
)
from app.business.services.bitacora_service import Actor, BitacoraComprasService
from app.business.services.categorizacion import (
    CadenaDeCategorizacion,
    CategoriaResuelta,
    ContextoDeCategorizacion,
    ReglasDelTitular,
    SugerenciaDelComercio,
)
from app.business.services.ciclo_comprobante import estado_de
from app.business.services.comercio_service import ComercioService
from app.business.services.presupuesto_service import PresupuestoService
from app.business.services.tipo_cambio_service import TipoCambioService
from app.data.models.compra import Compra
from app.data.models.comprobante import Comprobante
from app.data.models.enums import (
    EstadoCompra,
    EstadoComprobante,
    EstadoPresupuesto,
    Moneda,
    OrigenCompra,
)
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.comprobante_repository import ComprobanteRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.tipo_cambio_repository import TipoCambioRepository

_MONEDA_BASE = Moneda.CRC
_TASA_IVA = Decimal("0.13")
_CENTIMOS = Decimal("0.01")
_TIPO_COMPRA = "COMPRA"


@dataclass(frozen=True)
class ConciliarComprobanteComando:
    """Orden que recibe el negocio para conciliar un comprobante ya recibido.

    Trae lo que el lector extrajo del mensaje, no el mensaje ni la entidad: el
    servicio busca el `Comprobante` por su id -y por su dueño- en vez de
    recibirlo armado, así que no hay forma de pasarle uno ajeno.

    Los campos del parseo admiten `None`: un comprobante incompleto es un caso
    normal del negocio -va a revisión manual-, no un error.
    """

    usuario_id: int
    comprobante_id: int
    comercio: str | None
    monto: Decimal | None
    moneda: str | None
    fecha: datetime | None
    ultimos_cuatro: str | None = None
    tipo_transaccion: str | None = _TIPO_COMPRA
    confianza: float = 1.0

    @property
    def motivo_no_conciliable(self) -> str | None:
        """Por qué este comprobante no puede convertirse en compra solo, o `None` si puede."""
        if self.tipo_transaccion != _TIPO_COMPRA:
            return f"La notificación no es una compra ({self.tipo_transaccion})."
        if not self.comercio:
            return "El comprobante no trae el comercio."
        if self.monto is None:
            return "El comprobante no trae el monto."
        if self.fecha is None:
            return "El comprobante no trae la fecha."
        if not self.moneda or self.moneda not in Moneda.__members__:
            # Una moneda que el sistema no reconoce no se inventa a qué tasa vale.
            return f"El sistema no reconoce la moneda {self.moneda!r}."
        return None


@dataclass(frozen=True)
class ResultadoConciliacion:
    """Lo que produjo conciliar un comprobante.

    `compra_id` en `None` no es un error: el comprobante quedó en revisión
    manual, o pendiente de que exista el tipo de cambio de su fecha. `estado`
    y `motivo` dicen cuál de los dos.
    """

    comprobante_id: int
    estado: EstadoComprobante
    compra_id: int | None = None
    requiere_revision: bool = False
    presupuesto_alertado: bool = False
    motivo: str | None = None


@dataclass(frozen=True)
class CompraCorregida:
    """Cómo quedó una compra después de una corrección manual."""

    compra_id: int
    metodo_pago_id: int | None
    categoria_id: int | None
    requiere_revision: bool


@dataclass(frozen=True)
class CompraAnulada:
    """El resultado de anular una compra: qué presupuestos recuperaron su monto."""

    compra_id: int
    estado: EstadoCompra
    presupuestos_devueltos: tuple[int, ...]


@dataclass(frozen=True)
class _CompraEscrita:
    """Estado intermedio: lo que la transacción dejó listo para confirmar."""

    compra: Compra
    metodo_pago: MetodoPago | None
    categoria: CategoriaResuelta | None
    presupuesto_id: int | None
    consumido_antes: Decimal | None
    consumido_despues: Decimal | None
    alerta_presupuesto: bool


class ConciliacionService:
    """Aplica el Proceso 2 del dominio sobre un comprobante ya recibido."""

    def __init__(
        self,
        compra_repository: CompraRepository,
        linea_compra_repository: LineaCompraRepository,
        metodo_pago_repository: MetodoPagoRepository,
        regla_categorizacion_repository: ReglaCategorizacionRepository,
        presupuesto_repository: PresupuestoRepository,
        categoria_repository: CategoriaRepository,
        comercio_categoria_repository: ComercioCategoriaRepository,
        tipo_cambio_repository: TipoCambioRepository,
        comprobante_repository: ComprobanteRepository,
        comercio_service: ComercioService,
        tipo_cambio_service: TipoCambioService | None,
        bitacora: BitacoraComprasService,
    ) -> None:
        self.compras = compra_repository
        self.lineas = linea_compra_repository
        self.metodos_pago = metodo_pago_repository
        self.reglas = regla_categorizacion_repository
        self.presupuestos = presupuesto_repository
        self.categorias = categoria_repository
        self.sugerencias = comercio_categoria_repository
        self.tipos_cambio = tipo_cambio_repository
        self.comprobantes = comprobante_repository
        self.comercios_servicio = comercio_service
        self.tipo_cambio_servicio = tipo_cambio_service
        self.bitacora = bitacora

    def conciliar(self, comando: ConciliarComprobanteComando) -> ResultadoConciliacion:
        """Corre los pasos 3-9 del Proceso 2 sobre un comprobante del titular.

        Reglas que aplica, en este orden:

        - El comprobante tiene que existir **y ser del titular** que lo pide.
        - Si todavía está `RECIBIDO`, se cierra el parseo: por debajo de 0.75
          de confianza, o si no es una compra, o si le falta comercio, monto,
          fecha o una moneda reconocida, queda en `REVISION_MANUAL` y no se
          inventa nada.
        - Solo un comprobante `PARSEADO` se concilia. Uno `PROCESADO` o
          `FALLIDO` se rechaza: es lo que hace idempotente a la ingesta.
        - Una compra en moneda extranjera **sin tipo de cambio para su fecha
          queda pendiente** hasta que la tasa exista. No se usa una aproximada.
        - Si los últimos cuatro no casan con ningún método de pago, o ninguna
          fuente resuelve la categoría, la compra se crea igual pero marcada
          `requiere_revision`.
        - Si la escritura falla, se revierte todo y se cuenta un intento; al
          tercero el comprobante pasa a `FALLIDO`.
        """
        comprobante = self.comprobantes.obtener_de_usuario(
            comando.comprobante_id, comando.usuario_id
        )
        if comprobante is None:
            raise RecursoNoEncontrado(
                f"El comprobante {comando.comprobante_id} no existe en esta cuenta."
            )

        # Paso 3: cerrar el parseo.
        if comprobante.estado == EstadoComprobante.RECIBIDO:
            motivo = comando.motivo_no_conciliable
            estado_de(comprobante).parsear(comando.confianza, motivo is None, motivo)
            self.comprobantes.sesion.commit()
        if comprobante.estado == EstadoComprobante.REVISION_MANUAL:
            return self._sin_compra(comprobante)

        estado_de(comprobante).asegurar_conciliable()

        moneda = Moneda(comando.moneda)
        fecha = comando.fecha.date()
        total = comando.monto

        # Paso 4: emparejar método de pago -nunca se crea uno solo, ver MetodoPago.
        metodo_pago = None
        if comando.ultimos_cuatro:
            metodo_pago = self.metodos_pago.buscar_por_ultimos_cuatro(
                comando.usuario_id, comando.ultimos_cuatro
            )

        # Paso 5: resolver el comercio (catálogo compartido, confirma con su propio commit).
        comercio = self.comercios_servicio.resolver_o_crear(comando.comercio)

        tipo_cambio_aplicado = Decimal("1")
        if moneda != _MONEDA_BASE:
            tasa = self._tasa_de_conversion(moneda, fecha)
            if tasa is None:
                estado_de(comprobante).dejar_pendiente(
                    f"No hay tipo de cambio {moneda.value}→{_MONEDA_BASE.value} para el "
                    f"{fecha.isoformat()}. El comprobante queda pendiente hasta que exista."
                )
                self.comprobantes.sesion.commit()
                return self._sin_compra(comprobante)
            tipo_cambio_aplicado = tasa

        try:
            escrita = self._escribir_la_compra(
                comando, comprobante, comercio, metodo_pago, moneda, fecha, total,
                tipo_cambio_aplicado,
            )  # fmt: skip
            # Un solo commit: todo lo de arriba, o nada.
            self.comprobantes.sesion.commit()
        except Exception as error:
            self.comprobantes.sesion.rollback()
            self._contar_intento_fallido(comando, error)
            raise

        compra = escrita.compra
        self._escribir_bitacora(comando, escrita, comercio.nombre, comercio.nombre_normalizado)

        return ResultadoConciliacion(
            comprobante_id=comprobante.id,
            estado=comprobante.estado,
            compra_id=compra.id,
            requiere_revision=compra.requiere_revision,
            presupuesto_alertado=escrita.alerta_presupuesto,
        )

    def _escribir_la_compra(
        self,
        comando: ConciliarComprobanteComando,
        comprobante: Comprobante,
        comercio,
        metodo_pago: MetodoPago | None,
        moneda: Moneda,
        fecha: date,
        total: Decimal,
        tipo_cambio_aplicado: Decimal,
    ) -> _CompraEscrita:
        """Pasos 6-9: las cinco escrituras, sin confirmar. El `commit` es de quien llama."""
        # Paso 6 (categorización): la cadena de la ingesta -reglas del titular
        # por prioridad y, si ninguna coincide, la sugerencia del comercio.
        categoria = self._cadena_de_categorizacion().resolver(
            ContextoDeCategorizacion(
                usuario_id=comando.usuario_id,
                comercio_id=comercio.id,
                comercio_normalizado=comercio.nombre_normalizado,
            )
        )
        categoria_id = categoria.categoria_id if categoria else None
        requiere_revision = metodo_pago is None or categoria_id is None

        compra = Compra(
            usuario_id=comando.usuario_id,
            comercio_id=comercio.id,
            metodo_pago_id=metodo_pago.id if metodo_pago else None,
            fecha=fecha,
            descripcion=comercio.nombre,
            moneda=moneda,
            estado=EstadoCompra.REGISTRADA,
            origen=OrigenCompra.INGESTA_CORREO,
            subtotal=total,
            descuento=Decimal("0"),
            impuesto=Decimal("0"),
            impuesto_desglosado=False,
            total=total,
            tipo_cambio_aplicado=tipo_cambio_aplicado,
            total_moneda_base=(total * tipo_cambio_aplicado).quantize(
                _CENTIMOS, rounding=ROUND_HALF_UP
            ),
            requiere_revision=requiere_revision,
        )
        self.compras.agregar(compra)  # flush: ya tiene compra.id de acá en adelante

        self.lineas.agregar(
            LineaCompra(
                compra_id=compra.id,
                usuario_id=comando.usuario_id,
                categoria_id=categoria_id,
                descripcion=comercio.nombre,
                cantidad=Decimal("1"),
                precio_unitario=total,
                descuento=Decimal("0"),
                exento_impuesto=False,
                subtotal=total,
                categorizada_automaticamente=categoria_id is not None,
            )
        )

        # Paso 7: el contador de la regla que acertó, si hubo alguna.
        if categoria is not None and categoria.regla is not None:
            categoria.regla.veces_aplicada += 1

        # Paso 8: el consumo del presupuesto afectado y la alerta de umbral.
        alerta_presupuesto = False
        presupuesto_id = consumido_antes = consumido_despues = None
        if categoria_id is not None:
            presupuesto = self.presupuestos.buscar(
                comando.usuario_id, categoria_id, fecha.year, fecha.month
            )
            # Solo se acumula si el presupuesto está en la MISMA moneda que la
            # compra -mezclar monedas en una suma daría un número inventado.
            if presupuesto is not None and presupuesto.moneda == moneda:
                presupuesto_id = presupuesto.id
                consumido_antes = presupuesto.monto_consumido
                porcentaje_antes, _ = PresupuestoService.calcular_estado(
                    consumido_antes, presupuesto.monto_limite, presupuesto.umbral_alerta
                )
                presupuesto.monto_consumido = presupuesto.monto_consumido + total
                consumido_despues = presupuesto.monto_consumido
                _, estado_despues = PresupuestoService.calcular_estado(
                    consumido_despues, presupuesto.monto_limite, presupuesto.umbral_alerta
                )
                # Una sola vez: solo si antes de esta compra estaba bajo el umbral.
                alerta_presupuesto = (
                    estado_despues != EstadoPresupuesto.EN_RANGO
                    and porcentaje_antes < presupuesto.umbral_alerta
                )

        # Paso 9: el comprobante pasa a PROCESADO y queda ligado a su compra.
        estado_de(comprobante).procesar(compra.id)

        return _CompraEscrita(
            compra=compra,
            metodo_pago=metodo_pago,
            categoria=categoria,
            presupuesto_id=presupuesto_id,
            consumido_antes=consumido_antes,
            consumido_despues=consumido_despues,
            alerta_presupuesto=alerta_presupuesto,
        )

    def _contar_intento_fallido(
        self, comando: ConciliarComprobanteComando, error: Exception
    ) -> None:
        """Cuenta el intento después del rollback, en su propia transacción.

        Va aparte a propósito: si viajara en la transacción que falló, se
        revertiría con ella y el comprobante podría reintentarse para siempre.
        Si contar el intento también falla -la base se cayó, por ejemplo- no se
        tapa el error original, que es el que explica qué pasó.
        """
        with contextlib.suppress(Exception):
            comprobante = self.comprobantes.obtener_de_usuario(
                comando.comprobante_id, comando.usuario_id
            )
            if comprobante is None:
                return
            estado_de(comprobante).registrar_fallo(f"{type(error).__name__}: {error}")
            self.comprobantes.sesion.commit()

    def _sin_compra(self, comprobante: Comprobante) -> ResultadoConciliacion:
        return ResultadoConciliacion(
            comprobante_id=comprobante.id,
            estado=comprobante.estado,
            motivo=comprobante.motivo_fallo,
        )

    def anular(self, usuario_id: int, compra_id: int) -> CompraAnulada:
        """Anula una compra y le devuelve su monto a los presupuestos que impactó.

        Reglas que aplica:

        - La compra tiene que existir y ser del titular.
        - Nunca se borra físicamente: pasa a `ANULADA` y sigue en el historial.
        - Una compra ya anulada no se anula dos veces -devolvería el monto dos
          veces.
        - Cada categoría recupera exactamente lo que sus renglones le habían
          sumado al presupuesto de ese período, y el consumido nunca queda
          negativo.
        - El comprobante que la originó sigue `PROCESADO`: la ingesta ya hizo
          su trabajo, y reabrirlo volvería a crear el gasto que se acaba de
          anular.
        """
        compra = self.compras.obtener_de_usuario(compra_id, usuario_id)
        if compra is None:
            raise RecursoNoEncontrado(f"La compra {compra_id} no existe en esta cuenta.")
        if compra.estado == EstadoCompra.ANULADA:
            raise CompraYaAnulada(f"La compra {compra_id} ya está anulada.")

        por_categoria: dict[int, Decimal] = {}
        for linea in self.lineas.listar_de_compra(compra.id):
            if linea.categoria_id is None:
                continue  # sin categoría nunca impactó ningún presupuesto
            acumulado = por_categoria.get(linea.categoria_id, Decimal("0"))
            por_categoria[linea.categoria_id] = acumulado + self._monto_que_impacto(compra, linea)

        impactos: list[dict] = []
        for categoria_id, monto in por_categoria.items():
            presupuesto = self.presupuestos.buscar(
                usuario_id, categoria_id, compra.fecha.year, compra.fecha.month
            )
            if presupuesto is None or presupuesto.moneda != compra.moneda:
                continue
            consumido_antes = presupuesto.monto_consumido
            presupuesto.monto_consumido = max(Decimal("0"), consumido_antes - monto)
            impactos.append(
                {
                    "presupuesto_id": presupuesto.id,
                    "consumido_antes": str(consumido_antes),
                    "consumido_despues": str(presupuesto.monto_consumido),
                }
            )

        estado_anterior = compra.estado
        compra.estado = EstadoCompra.ANULADA
        compra.requiere_revision = False

        # Un solo commit: el cambio de estado y la devolución a cada presupuesto.
        self.compras.sesion.commit()

        actor = Actor(tipo="TITULAR", usuario_id=usuario_id)

        def registrar(tipo: str, datos: dict) -> None:
            self.bitacora.registrar_evento(
                compra_id=compra.id,
                usuario_id=usuario_id,
                estado_actual=compra.estado.value,
                tipo=tipo,
                datos=datos,
                actor=actor,
            )

        registrar("ANULACION", {"total_devuelto": str(compra.total)})
        registrar(
            "CAMBIO_ESTADO", {"anterior": estado_anterior.value, "nuevo": compra.estado.value}
        )
        for impacto in impactos:
            registrar("IMPACTO_PRESUPUESTO", impacto)

        return CompraAnulada(
            compra_id=compra.id,
            estado=compra.estado,
            presupuestos_devueltos=tuple(impacto["presupuesto_id"] for impacto in impactos),
        )

    @staticmethod
    def _monto_que_impacto(compra: Compra, linea: LineaCompra) -> Decimal:
        """Lo que este renglón le sumó a su presupuesto cuando se registró la compra.

        Tiene que ser el mismo cálculo que hizo quien lo sumó: una compra con
        desglose (`RegistrarCompraService`) suma `subtotal + impuesto` de cada
        renglón; una ingerida por correo trae el impuesto ya adentro del total.
        """
        if not compra.impuesto_desglosado or linea.exento_impuesto:
            return linea.subtotal
        impuesto = (linea.subtotal * _TASA_IVA).quantize(_CENTIMOS, rounding=ROUND_HALF_UP)
        return linea.subtotal + impuesto

    def recategorizar_compras_de_comercio(
        self, usuario_id: int, comercio_id: int, categoria_id: int
    ) -> int:
        """Aplica una categoría recién asignada a un comercio sobre las compras que
        ya se conciliaron sin categoría -"corregir crea la regla" también corrige
        lo que ya pasó, no solo lo que viene.

        Se llama después de `ComercioService.asignar_categoria`, desde el mismo
        endpoint. Solo toca renglones sin categoría -una compra que sí tenía
        una (una regla la puso, o una corrección anterior) no se pisa sola- y
        nunca una compra anulada. Devuelve cuántas compras se corrigieron.
        """
        afectadas = [
            (linea, compra)
            for linea, compra in self.lineas.listar_sin_categoria_de_comercio(
                usuario_id, comercio_id
            )
            if compra.estado != EstadoCompra.ANULADA
        ]
        if not afectadas:
            return 0

        actor = Actor(tipo="TITULAR", usuario_id=usuario_id)
        for linea, compra in afectadas:
            categoria_anterior_id = linea.categoria_id
            linea.categoria_id = categoria_id
            linea.categorizada_automaticamente = False
            compra.requiere_revision = compra.metodo_pago_id is None

            presupuesto = self.presupuestos.buscar(
                usuario_id, categoria_id, compra.fecha.year, compra.fecha.month
            )
            consumido_antes = consumido_despues = None
            if presupuesto is not None and presupuesto.moneda == compra.moneda:
                consumido_antes = presupuesto.monto_consumido
                presupuesto.monto_consumido = presupuesto.monto_consumido + compra.total
                consumido_despues = presupuesto.monto_consumido

            self.comprobantes.sesion.commit()

            self.bitacora.registrar_evento(
                compra_id=compra.id,
                usuario_id=usuario_id,
                estado_actual=compra.estado.value,
                tipo="CORRECCION_MANUAL",
                datos={
                    "linea_id": linea.id,
                    "categoria_anterior_id": categoria_anterior_id,
                    "categoria_nueva_id": categoria_id,
                },
                actor=actor,
            )
            if presupuesto is not None and consumido_antes is not None:
                self.bitacora.registrar_evento(
                    compra_id=compra.id,
                    usuario_id=usuario_id,
                    estado_actual=compra.estado.value,
                    tipo="IMPACTO_PRESUPUESTO",
                    datos={
                        "presupuesto_id": presupuesto.id,
                        "consumido_antes": str(consumido_antes),
                        "consumido_despues": str(consumido_despues),
                    },
                    actor=actor,
                )

        return len(afectadas)

    def resolver_revision(
        self,
        usuario_id: int,
        compra_id: int,
        metodo_pago_id: int | None,
        categoria_id: int | None,
    ) -> CompraCorregida:
        """Corrige a mano el método de pago y/o la categoría de una compra real
        -pensada para las que quedaron `requiere_revision=True` porque la
        ingesta no pudo resolver alguno de los dos solo, aunque corre igual
        sobre cualquier compra si hiciera falta corregir un emparejamiento
        equivocado.

        Ninguno de los dos campos se inventa el otro: si solo se manda uno,
        el otro queda tal como estaba. Si la compra ya tenía categoría y se
        manda una distinta, se corrige el dato pero **no se toca ningún
        presupuesto** -moverla de un presupuesto a otro exigiría revertir lo
        que ya se acumuló en el anterior, que es una operación aparte que
        esto no cubre. Solo se acumula cuando la categoría estaba vacía: ese
        gasto todavía no había impactado ningún presupuesto.

        Devuelve un `CompraCorregida`, no la entidad: lo que cruza hacia la
        presentación es el resultado de la corrección, no la fila del ORM.
        """
        if metodo_pago_id is None and categoria_id is None:
            raise CorreccionVacia("Hay que corregir al menos el método de pago o la categoría.")

        compra = self.compras.obtener_de_usuario(compra_id, usuario_id)
        if compra is None:
            raise RecursoNoEncontrado(f"La compra {compra_id} no existe en esta cuenta.")
        if compra.estado == EstadoCompra.ANULADA:
            raise CompraYaAnulada(f"La compra {compra_id} está anulada: no se corrige.")

        actor = Actor(tipo="TITULAR", usuario_id=usuario_id)
        metodo_pago_anterior_id = compra.metodo_pago_id

        if metodo_pago_id is not None:
            metodo_pago = self.metodos_pago.obtener_de_usuario(metodo_pago_id, usuario_id)
            if metodo_pago is None:
                raise RecursoNoEncontrado(
                    f"El método de pago {metodo_pago_id} no existe en esta cuenta."
                )
            if not metodo_pago.activo:
                raise MetodoPagoInactivo("Ese método de pago está desactivado.")
            # Por la relación, no por la columna: `compra` ya pudo haber
            # llegado con `metodo_pago` cargado, y asignar solo
            # `metodo_pago_id` dejaría ese atributo desactualizado -la
            # siguiente lectura en esta misma sesión seguiría viendo el
            # método de pago viejo.
            compra.metodo_pago = metodo_pago

        lineas = self.lineas.listar_de_compra(compra.id)
        linea_principal = lineas[0] if lineas else None
        categoria_anterior_id = linea_principal.categoria_id if linea_principal else None
        presupuesto_id = consumido_antes = consumido_despues = None

        if categoria_id is not None:
            categoria = self.categorias.obtener_de_usuario(categoria_id, usuario_id)
            if categoria is None:
                raise RecursoNoEncontrado(f"La categoría {categoria_id} no existe en esta cuenta.")
            if not categoria.es_hoja:
                raise CategoriaNoEsHoja("La categoría tiene que ser una hoja, no un grupo.")
            if linea_principal is None:
                raise ReglaDeNegocioViolada("Esta compra no tiene ningún renglón que categorizar.")
            # Por la relación, no por la columna -mismo motivo que
            # `compra.metodo_pago` unas líneas arriba.
            linea_principal.categoria = categoria
            linea_principal.categorizada_automaticamente = False

            if categoria_anterior_id is None:
                presupuesto = self.presupuestos.buscar(
                    usuario_id, categoria.id, compra.fecha.year, compra.fecha.month
                )
                if presupuesto is not None and presupuesto.moneda == compra.moneda:
                    presupuesto_id = presupuesto.id
                    consumido_antes = presupuesto.monto_consumido
                    presupuesto.monto_consumido = presupuesto.monto_consumido + compra.total
                    consumido_despues = presupuesto.monto_consumido

        # SQLAlchemy solo sincroniza la columna de la llave foránea (`metodo_pago_id`,
        # `categoria_id`) a partir de la relación en el flush -asignar
        # `compra.metodo_pago`/`linea_principal.categoria` arriba no las deja
        # listas todavía para las comparaciones de abajo sin este flush.
        self.compras.sesion.flush()

        requiere_revision_antes = compra.requiere_revision
        compra.requiere_revision = compra.metodo_pago_id is None or (
            linea_principal is None or linea_principal.categoria_id is None
        )

        self.comprobantes.sesion.commit()

        categoria_nueva_id = linea_principal.categoria_id if linea_principal else None
        self.bitacora.registrar_evento(
            compra_id=compra.id,
            usuario_id=usuario_id,
            estado_actual=compra.estado.value,
            tipo="CORRECCION_MANUAL",
            datos={
                "metodo_pago_anterior_id": metodo_pago_anterior_id,
                "metodo_pago_nuevo_id": compra.metodo_pago_id,
                "categoria_anterior_id": categoria_anterior_id,
                "categoria_nueva_id": categoria_nueva_id,
                "requiere_revision_antes": requiere_revision_antes,
                "requiere_revision_despues": compra.requiere_revision,
            },
            actor=actor,
        )
        if presupuesto_id is not None:
            self.bitacora.registrar_evento(
                compra_id=compra.id,
                usuario_id=usuario_id,
                estado_actual=compra.estado.value,
                tipo="IMPACTO_PRESUPUESTO",
                datos={
                    "presupuesto_id": presupuesto_id,
                    "consumido_antes": str(consumido_antes),
                    "consumido_despues": str(consumido_despues),
                },
                actor=actor,
            )

        return CompraCorregida(
            compra_id=compra.id,
            metodo_pago_id=compra.metodo_pago_id,
            categoria_id=categoria_nueva_id,
            requiere_revision=compra.requiere_revision,
        )

    def _cadena_de_categorizacion(self) -> CadenaDeCategorizacion:
        """La cadena de la ingesta: reglas del titular y, después, sugerencia del comercio.

        No lleva el eslabón del titular eligiendo a mano -en la ingesta nadie
        eligió nada todavía-; el registro manual arma la suya con ese eslabón
        delante (ver `RegistrarCompraService`). Se arma una por conciliación
        porque `ReglasDelTitular` recuerda las reglas que leyó.
        """
        return CadenaDeCategorizacion(
            [
                ReglasDelTitular(self.reglas.listar_activas_ordenadas),
                SugerenciaDelComercio(self.comercios_servicio.categoria_sugerida_para),
            ]
        )

    def _tasa_de_conversion(self, moneda: Moneda, fecha: date) -> Decimal | None:
        """La tasa de esa fecha, o `None` si todavía no existe.

        Primero el histórico propio (`tipo_cambio`): si la tasa de ese día ya
        se guardó, es la que vale y no se le vuelve a preguntar a nadie. Si no
        está, se le pide al Banco Central y se guarda como histórico real.

        `None` -no hay servicio configurado, o el proveedor no respondió- no se
        convierte en una tasa de 1: la propuesta de dominio es explícita en que
        un comprobante en moneda extranjera sin tipo de cambio **queda
        pendiente hasta que la tasa exista**. Usar 1 registraría una compra de
        50 dólares como si fueran 50 colones.
        """
        guardada = self.tipos_cambio.buscar(moneda, _MONEDA_BASE, fecha)
        if guardada is not None:
            return guardada.tasa
        if self.tipo_cambio_servicio is None:
            return None
        try:
            tipo_de_cambio = self.tipo_cambio_servicio.obtener(fecha)
        except ErrorDeProveedorExterno:
            return None
        self.tipos_cambio.guardar_tasa(
            moneda_origen=moneda,
            moneda_destino=_MONEDA_BASE,
            fecha=tipo_de_cambio.fecha,
            tasa=tipo_de_cambio.venta,
            fuente="BCCR",
        )
        return tipo_de_cambio.venta

    def _escribir_bitacora(
        self,
        comando: ConciliarComprobanteComando,
        escrita: _CompraEscrita,
        comercio_nombre: str,
        comercio_normalizado: str,
    ) -> None:
        compra = escrita.compra
        metodo_pago_id = escrita.metodo_pago.id if escrita.metodo_pago else None
        categoria = escrita.categoria
        actor = Actor(tipo="SERVICIO", nombre="ingesta-correo")

        def registrar(tipo: str, datos: dict) -> None:
            self.bitacora.registrar_evento(
                compra_id=compra.id,
                usuario_id=comando.usuario_id,
                estado_actual=compra.estado.value,
                tipo=tipo,
                datos=datos,
                actor=actor,
            )

        registrar(
            "PARSEO_COMPROBANTE",
            {
                "confianza": comando.confianza,
                "campos_extraidos": [
                    campo
                    for campo in ("comercio", "monto", "moneda", "fecha", "ultimos_cuatro")
                    if getattr(comando, campo, None) is not None
                ],
            },
        )
        registrar(
            "EMPAREJAMIENTO_METODO_PAGO",
            {
                "ultimos_cuatro": comando.ultimos_cuatro,
                "resultado": "EMPAREJADO" if metodo_pago_id else "SIN_COINCIDENCIA",
                "metodo_pago_id": metodo_pago_id,
            },
        )
        registrar(
            "RESOLUCION_COMERCIO",
            {
                "nombre_crudo": comando.comercio,
                "nombre_normalizado": comercio_normalizado,
                "comercio_id": compra.comercio_id,
            },
        )
        registrar(
            "CATEGORIZACION_AUTOMATICA",
            {
                "origen": categoria.origen.value if categoria else None,
                "regla_id": categoria.regla.id if categoria and categoria.regla else None,
                "categoria_id": categoria.categoria_id if categoria else None,
            },
        )
        if compra.tipo_cambio_aplicado != Decimal("1"):
            registrar(
                "CONVERSION_MONEDA",
                {
                    "moneda_origen": compra.moneda.value,
                    "moneda_destino": _MONEDA_BASE.value,
                    "tasa": str(compra.tipo_cambio_aplicado),
                    "monto_antes": str(compra.total),
                    "monto_despues": str(compra.total_moneda_base),
                },
            )
        registrar(
            "CAMBIO_ESTADO",
            {"anterior": None, "nuevo": compra.estado.value},
        )
        if escrita.presupuesto_id is not None and escrita.consumido_antes is not None:
            registrar(
                "IMPACTO_PRESUPUESTO",
                {
                    "presupuesto_id": escrita.presupuesto_id,
                    "consumido_antes": str(escrita.consumido_antes),
                    "consumido_despues": str(escrita.consumido_despues),
                },
            )
        if escrita.alerta_presupuesto:
            registrar("ALERTA_PRESUPUESTO", {"presupuesto_id": escrita.presupuesto_id})
        if compra.requiere_revision:
            registrar(
                "REVISION_REQUERIDA",
                {
                    "motivo": "SIN_METODO_DE_PAGO" if metodo_pago_id is None else "SIN_CATEGORIA",
                },
            )
