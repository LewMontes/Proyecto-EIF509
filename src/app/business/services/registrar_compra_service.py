"""Proceso 1 del dominio: registro de una compra con desglose y categorización.

Es el proceso que el titular ejecuta a mano cuando la compra no llegó por
correo -un tiquete de papel, una compra en efectivo, una factura que el banco
no notificó-. A diferencia del Proceso 2, acá sí hay desglose real: varios
renglones, cada uno con su cantidad, su precio unitario, su descuento y su
propia categoría, y el impuesto se calcula en vez de venir incluido en un
total opaco (ver `docs/propuesta-dominio.md`, «Qué traen realmente los
comprobantes»: una compra ingerida por correo nunca puede desglosarse porque
la notificación bancaria no trae el detalle de qué se compró).

**También es transaccional.** Escribe en cuatro tablas -`compra`,
`linea_compra`, `regla_categorizacion` (el contador de la regla que acertó) y
`presupuesto` (el consumo de cada categoría afectada)- y las escrituras van en
un único `commit` al final, por el mismo motivo que la conciliación: una
compra registrada que no impactó el presupuesto de sus categorías es una
inconsistencia invisible, que solo aparecería cuadrando a mano.

Comparte con `ConciliacionService` la cadena de categorización
(`categorizacion.primera_regla_que_coincide`) y el cálculo del estado de un
presupuesto (`PresupuestoService.calcular_estado`): que la misma compra caiga
en una categoría distinta según por dónde entró sería un error que nadie
notaría hasta cuadrar un reporte.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.business.errors import (
    CategoriaInactiva,
    CategoriaNoEsHoja,
    CompraSinRenglones,
    CuadreFueraDeTolerancia,
    DatosInvalidos,
    DescuentoExcedido,
    FechaFutura,
    MetodoPagoInactivo,
    RecursoNoEncontrado,
    RenglonSinCategoria,
    TipoDeCambioRequerido,
    UsuarioInactivo,
)
from app.business.services.bitacora_service import Actor, BitacoraComprasService
from app.business.services.categorizacion import (
    CadenaDeCategorizacion,
    CategoriaElegidaPorElTitular,
    ContextoDeCategorizacion,
    ReglasDelTitular,
    SugerenciaDelComercio,
)
from app.business.services.comercio_service import ComercioService
from app.business.services.presupuesto_service import PresupuestoService
from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra, EstadoPresupuesto, Moneda, OrigenCompra
from app.data.models.linea_compra import LineaCompra
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.usuario_repository import UsuarioRepository

MONEDA_BASE = Moneda.CRC
TASA_IVA = Decimal("0.13")
# La propuesta de dominio fija esta tolerancia: si el titular declara el total
# impreso en el recibo, el calculado no puede diferir en más de un colón. Un
# céntimo de diferencia es redondeo del comercio; más que eso es un renglón
# mal digitado.
DIFERENCIA_MAXIMA_CONTRA_EL_RECIBO = Decimal("1")
LARGO_MAXIMO_DESCRIPCION = 255
_CENTIMOS = Decimal("0.01")


def _redondear(monto: Decimal) -> Decimal:
    """Dos decimales, redondeo comercial.

    Con punto flotante un reporte de gastos no cuadra por céntimos; con
    `Decimal` y `ROUND_HALF_UP` la cuenta da lo mismo que la haría una persona
    con una calculadora, que es contra lo que el titular la va a comparar.
    """
    return monto.quantize(_CENTIMOS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LineaDeCompraComando:
    """Un renglón del desglose, tal como lo captura el titular.

    `categoria_id` en `None` significa «que el sistema sugiera»: se resuelve
    con la cadena de categorización, igual que en la ingesta por correo. No
    significa «sin categoría»: una compra que queda REGISTRADA no admite
    renglones sin clasificar.
    """

    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    descuento: Decimal = Decimal("0")
    exento_impuesto: bool = False
    categoria_id: int | None = None


@dataclass(frozen=True)
class RegistrarCompraComando:
    """Orden que recibe el negocio para registrar una compra a mano.

    Es una dataclass propia y no un modelo de Pydantic: si el servicio
    recibiera modelos de FastAPI, el dominio quedaría amarrado a la forma de
    la API y no se podría llamar desde un script ni desde una importación
    masiva de tiquetes.
    """

    usuario_id: int
    comercio_id: int
    fecha: date
    lineas: tuple[LineaDeCompraComando, ...]
    moneda: Moneda = Moneda.CRC
    metodo_pago_id: int | None = None
    descripcion: str | None = None
    # Descuento sobre el total de la compra, no sobre un renglón. No se
    # prorratea entre renglones: se resta después de sumar, para que el
    # titular vea de dónde salió la rebaja (ver la propuesta de dominio).
    descuento: Decimal = Decimal("0")
    # El total impreso en el recibo, si el titular lo transcribió. Sirve para
    # cuadrar: no se usa como total, se compara contra el calculado.
    total_declarado: Decimal | None = None
    # La tasa de la fecha de la compra, cuando la moneda no es la base. Se
    # recibe explícita en vez de consultarla: el titular está capturando una
    # compra que pudo ocurrir hace meses, y la tasa de hoy no es la que pagó.
    tipo_cambio_aplicado: Decimal | None = None


@dataclass(frozen=True)
class LineaRegistrada:
    """Un renglón ya calculado y clasificado, como sale del negocio."""

    linea_id: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    descuento: Decimal
    exento_impuesto: bool
    subtotal: Decimal
    impuesto: Decimal
    categoria_id: int
    categoria_nombre: str
    categorizada_automaticamente: bool


@dataclass(frozen=True)
class CompraRegistrada:
    """El resultado del proceso, sin exponer ninguna entidad del ORM.

    Es lo que el router convierte a su respuesta HTTP. Que sea inmutable no
    es decorativo: es el resultado de una transacción que ya se confirmó, y
    modificarlo después no cambiaría nada en la base -daría la falsa
    impresión de que sí.
    """

    compra_id: int
    fecha: date
    comercio_nombre: str
    metodo_pago_alias: str | None
    moneda: Moneda
    estado: EstadoCompra
    subtotal: Decimal
    descuento: Decimal
    impuesto: Decimal
    total: Decimal
    tipo_cambio_aplicado: Decimal
    total_moneda_base: Decimal
    lineas: tuple[LineaRegistrada, ...]
    presupuestos_alertados: tuple[int, ...]


@dataclass(frozen=True)
class _RenglonCalculado:
    """Estado intermedio: un renglón ya validado, calculado y categorizado."""

    comando: LineaDeCompraComando
    subtotal: Decimal
    impuesto: Decimal
    categoria_id: int
    categoria_nombre: str
    regla: ReglaCategorizacion | None


class RegistrarCompraService:
    """Aplica el Proceso 1 del dominio: captura manual con desglose."""

    def __init__(
        self,
        compra_repository: CompraRepository,
        linea_compra_repository: LineaCompraRepository,
        categoria_repository: CategoriaRepository,
        metodo_pago_repository: MetodoPagoRepository,
        presupuesto_repository: PresupuestoRepository,
        regla_categorizacion_repository: ReglaCategorizacionRepository,
        usuario_repository: UsuarioRepository,
        comercio_service: ComercioService,
        bitacora: BitacoraComprasService,
    ) -> None:
        self.compras = compra_repository
        self.lineas = linea_compra_repository
        self.categorias = categoria_repository
        self.metodos_pago = metodo_pago_repository
        self.presupuestos = presupuesto_repository
        self.reglas = regla_categorizacion_repository
        self.usuarios = usuario_repository
        self.comercios = comercio_service
        self.bitacora = bitacora

    def registrar(self, comando: RegistrarCompraComando) -> CompraRegistrada:
        """Registra una compra capturada a mano, con su desglose por renglón.

        Reglas y validaciones que aplica, en este orden:

        - El titular tiene que existir y estar activo.
        - La fecha no puede ser futura -un gasto que todavía no ocurrió no es
          un gasto.
        - La compra debe tener al menos un renglón: una compra sin renglones
          no tiene categoría ni monto, y no aparecería en ningún reporte.
        - Por renglón: descripción no vacía, cantidad mayor que cero, precio
          unitario no negativo, y el descuento del renglón no puede superar
          `cantidad × precio_unitario`.
        - El comercio, el método de pago y cada categoría tienen que existir,
          estar activos y **pertenecer al titular** -es la validación que
          impide tocar datos de otra cuenta pasando un id ajeno.
        - Solo se clasifica en categorías hoja: las padre totalizan, no
          reciben gasto directo.
        - Una compra `REGISTRADA` no admite renglones sin categoría. Si el
          titular no la indicó y la cadena de categorización tampoco la
          resuelve, la compra no se registra: si se permitiera, los reportes
          mostrarían menos gasto del real.
        - El descuento global no puede superar el subtotal.
        - Si el titular declaró el total del recibo, la diferencia contra el
          calculado no puede pasar de un colón.
        - Una compra en la moneda base no lleva conversión; una en otra
          moneda exige la tasa de su fecha -no se inventa una aproximada.
        """
        self._asegurar_usuario_activo(comando.usuario_id)
        self._validar_fecha(comando.fecha)

        if not comando.lineas:
            raise CompraSinRenglones("La compra tiene que tener al menos un renglón.")

        comercio = self.comercios.obtener(comando.comercio_id)
        metodo_pago = self._resolver_metodo_pago(comando.usuario_id, comando.metodo_pago_id)

        # Una sola cadena para toda la compra: su eslabón de reglas las lee una
        # vez y las reutiliza para todos los renglones, que comparten titular.
        cadena = self._cadena_de_categorizacion()
        renglones = [
            self._calcular_renglon(comando, linea, comercio.nombre_normalizado, cadena)
            for linea in comando.lineas
        ]

        subtotal = _redondear(sum((r.subtotal for r in renglones), Decimal("0")))
        impuesto = _redondear(sum((r.impuesto for r in renglones), Decimal("0")))
        descuento = self._validar_descuento_global(comando.descuento, subtotal)
        total = _redondear(subtotal - descuento + impuesto)
        self._validar_cuadre_contra_el_recibo(comando.total_declarado, total)

        tipo_cambio = self._resolver_tipo_de_cambio(comando)
        total_moneda_base = _redondear(total * tipo_cambio)

        compra = Compra(
            usuario_id=comando.usuario_id,
            comercio_id=comercio.id,
            metodo_pago_id=metodo_pago.id if metodo_pago else None,
            fecha=comando.fecha,
            descripcion=(comando.descripcion or comercio.nombre)[:LARGO_MAXIMO_DESCRIPCION],
            moneda=comando.moneda,
            estado=EstadoCompra.REGISTRADA,
            origen=OrigenCompra.MANUAL,
            subtotal=subtotal,
            descuento=descuento,
            impuesto=impuesto,
            # A diferencia de la ingesta por correo, acá el impuesto sí se
            # calculó renglón por renglón: no es un total opaco con el IVA
            # ya adentro.
            impuesto_desglosado=True,
            total=total,
            tipo_cambio_aplicado=tipo_cambio,
            total_moneda_base=total_moneda_base,
            # Nada quedó sin resolver: el titular eligió el comercio, y cada
            # renglón salió con categoría o la compra no se habría registrado.
            requiere_revision=False,
        )
        self.compras.agregar(compra)  # flush: ya tiene compra.id de acá en adelante

        lineas_registradas = tuple(self._escribir_renglon(compra, renglon) for renglon in renglones)

        for regla in {id(r.regla): r.regla for r in renglones if r.regla is not None}.values():
            regla.veces_aplicada += 1

        alertados, impactos = self._acumular_presupuestos(comando, renglones)

        # Un solo commit: la compra, sus renglones, los contadores de las
        # reglas y el consumo de cada presupuesto, o nada.
        self.compras.sesion.commit()

        self._escribir_bitacora(compra, renglones, lineas_registradas, impactos, alertados)

        return CompraRegistrada(
            compra_id=compra.id,
            fecha=compra.fecha,
            comercio_nombre=comercio.nombre,
            metodo_pago_alias=metodo_pago.alias if metodo_pago else None,
            moneda=compra.moneda,
            estado=compra.estado,
            subtotal=subtotal,
            descuento=descuento,
            impuesto=impuesto,
            total=total,
            tipo_cambio_aplicado=tipo_cambio,
            total_moneda_base=total_moneda_base,
            lineas=lineas_registradas,
            presupuestos_alertados=alertados,
        )

    # ---- validaciones ----

    def _validar_fecha(self, fecha: date) -> None:
        if fecha > date.today():
            raise FechaFutura("La fecha de la compra no puede ser futura.")

    def _validar_descuento_global(self, descuento: Decimal, subtotal: Decimal) -> Decimal:
        if descuento < 0:
            raise DatosInvalidos("El descuento de la compra no puede ser negativo.")
        if descuento > subtotal:
            raise DescuentoExcedido(
                f"El descuento ({descuento}) no puede superar el subtotal "
                f"de la compra ({subtotal})."
            )
        return _redondear(descuento)

    def _validar_cuadre_contra_el_recibo(
        self, total_declarado: Decimal | None, total: Decimal
    ) -> None:
        """El cuadre del paso 6 del proceso.

        No se usa el total declarado como total: se compara contra el
        calculado. Si se usara, un renglón mal digitado quedaría escondido
        detrás de un total correcto y el desglose por categoría -que es para
        lo que sirve capturar a mano- mentiría.
        """
        if total_declarado is None:
            return
        diferencia = abs(total - total_declarado)
        if diferencia > DIFERENCIA_MAXIMA_CONTRA_EL_RECIBO:
            raise CuadreFueraDeTolerancia(
                f"El total calculado ({total}) no cuadra con el del recibo ({total_declarado}): "
                f"se diferencian en {diferencia} y el máximo es "
                f"{DIFERENCIA_MAXIMA_CONTRA_EL_RECIBO}."
            )

    def _resolver_tipo_de_cambio(self, comando: RegistrarCompraComando) -> Decimal:
        if comando.moneda == MONEDA_BASE:
            # La base de datos lo exige además como CHECK: una compra en
            # colones con una tasa distinta de 1 sería una contradicción.
            if comando.tipo_cambio_aplicado not in (None, Decimal("1")):
                raise DatosInvalidos(
                    f"Una compra en {MONEDA_BASE.value} no lleva conversión de moneda."
                )
            return Decimal("1")
        if comando.tipo_cambio_aplicado is None:
            raise TipoDeCambioRequerido(
                f"Una compra en {comando.moneda.value} necesita el tipo de cambio de su fecha. "
                "No se usa el de hoy: no es el que se pagó."
            )
        if comando.tipo_cambio_aplicado <= 0:
            raise DatosInvalidos("El tipo de cambio tiene que ser mayor que cero.")
        return comando.tipo_cambio_aplicado

    def _resolver_metodo_pago(self, usuario_id: int, metodo_pago_id: int | None):
        if metodo_pago_id is None:
            return None
        metodo_pago = self.metodos_pago.obtener_de_usuario(metodo_pago_id, usuario_id)
        if metodo_pago is None:
            raise RecursoNoEncontrado(
                f"El método de pago {metodo_pago_id} no existe en esta cuenta."
            )
        if not metodo_pago.activo:
            raise MetodoPagoInactivo("Ese método de pago está desactivado.")
        return metodo_pago

    # ---- cálculo y categorización de un renglón ----

    def _calcular_renglon(
        self,
        comando: RegistrarCompraComando,
        linea: LineaDeCompraComando,
        comercio_normalizado: str,
        cadena: CadenaDeCategorizacion,
    ) -> _RenglonCalculado:
        descripcion = linea.descripcion.strip()
        if not descripcion:
            raise DatosInvalidos("La descripción de un renglón no puede venir vacía.")
        if linea.cantidad <= 0:
            raise DatosInvalidos(f"La cantidad de '{descripcion}' tiene que ser mayor que cero.")
        if linea.precio_unitario < 0:
            raise DatosInvalidos(f"El precio unitario de '{descripcion}' no puede ser negativo.")
        if linea.descuento < 0:
            raise DatosInvalidos(f"El descuento de '{descripcion}' no puede ser negativo.")

        bruto = linea.cantidad * linea.precio_unitario
        if linea.descuento > bruto:
            raise DescuentoExcedido(
                f"El descuento de '{descripcion}' ({linea.descuento}) supera el monto del "
                f"renglón ({_redondear(bruto)})."
            )

        subtotal = _redondear(bruto - linea.descuento)
        # Exento no es «sin impuesto por ahora»: es una propiedad del producto
        # (canasta básica, medicamentos). Por eso se captura por renglón y no
        # por compra.
        impuesto = Decimal("0") if linea.exento_impuesto else _redondear(subtotal * TASA_IVA)

        categoria_id, categoria_nombre, regla = self._resolver_categoria(
            comando.usuario_id, comando.comercio_id, linea, comercio_normalizado, cadena
        )
        return _RenglonCalculado(
            comando=linea,
            subtotal=subtotal,
            impuesto=impuesto,
            categoria_id=categoria_id,
            categoria_nombre=categoria_nombre,
            regla=regla,
        )

    def _cadena_de_categorizacion(self) -> CadenaDeCategorizacion:
        """La cadena del registro manual: el titular, sus reglas, la sugerencia del comercio.

        Los mismos dos últimos eslabones que la ingesta (`ConciliacionService`),
        con uno delante: acá sí hay una persona eligiendo, y su decisión se
        evalúa antes que cualquier regla.
        """
        return CadenaDeCategorizacion(
            [
                CategoriaElegidaPorElTitular(),
                ReglasDelTitular(self.reglas.listar_activas_ordenadas),
                SugerenciaDelComercio(self.comercios.categoria_sugerida_para),
            ]
        )

    def _resolver_categoria(
        self,
        usuario_id: int,
        comercio_id: int,
        linea: LineaDeCompraComando,
        comercio_normalizado: str,
        cadena: CadenaDeCategorizacion,
    ) -> tuple[int, str, ReglaCategorizacion | None]:
        """La categoría del renglón, según el primer eslabón de la cadena que la sepa.

        La cadena decide **cuál**; este método valida que esa categoría se
        pueda usar -que sea del titular, hoja y activa-, venga de donde venga.
        Si ningún eslabón la resuelve, la compra no se registra.
        """
        resuelta = cadena.resolver(
            ContextoDeCategorizacion(
                usuario_id=usuario_id,
                comercio_id=comercio_id,
                comercio_normalizado=comercio_normalizado,
                categoria_elegida_id=linea.categoria_id,
            )
        )
        if resuelta is None:
            raise RenglonSinCategoria(
                f"No hay categoría para el renglón '{linea.descripcion.strip()}' y una compra "
                "registrada no admite renglones sin clasificar: indicá una, o asignale una "
                "categoría sugerida al comercio."
            )
        categoria = self._categoria_del_titular(resuelta.categoria_id, usuario_id)
        return categoria.id, categoria.nombre, resuelta.regla

    def _categoria_del_titular(self, categoria_id: int, usuario_id: int):
        categoria = self.categorias.obtener_de_usuario(categoria_id, usuario_id)
        if categoria is None:
            raise RecursoNoEncontrado(f"La categoría {categoria_id} no existe en esta cuenta.")
        if not categoria.es_hoja:
            raise CategoriaNoEsHoja(
                f"'{categoria.nombre}' es una categoría padre; solo las hojas reciben gasto "
                "directo, las padre totalizan."
            )
        if not categoria.activa:
            raise CategoriaInactiva(f"La categoría '{categoria.nombre}' está desactivada.")
        return categoria

    # ---- escritura ----

    def _escribir_renglon(self, compra: Compra, renglon: _RenglonCalculado) -> LineaRegistrada:
        linea = LineaCompra(
            compra_id=compra.id,
            usuario_id=compra.usuario_id,
            categoria_id=renglon.categoria_id,
            descripcion=renglon.comando.descripcion.strip()[:LARGO_MAXIMO_DESCRIPCION],
            cantidad=renglon.comando.cantidad,
            precio_unitario=renglon.comando.precio_unitario,
            descuento=_redondear(renglon.comando.descuento),
            exento_impuesto=renglon.comando.exento_impuesto,
            subtotal=renglon.subtotal,
            categorizada_automaticamente=renglon.comando.categoria_id is None,
        )
        self.lineas.agregar(linea)
        return LineaRegistrada(
            linea_id=linea.id,
            descripcion=linea.descripcion,
            cantidad=linea.cantidad,
            precio_unitario=linea.precio_unitario,
            descuento=linea.descuento,
            exento_impuesto=linea.exento_impuesto,
            subtotal=linea.subtotal,
            impuesto=renglon.impuesto,
            categoria_id=renglon.categoria_id,
            categoria_nombre=renglon.categoria_nombre,
            categorizada_automaticamente=linea.categorizada_automaticamente,
        )

    def _acumular_presupuestos(
        self, comando: RegistrarCompraComando, renglones: list[_RenglonCalculado]
    ) -> tuple[tuple[int, ...], list[dict]]:
        """Impacta el presupuesto de cada categoría afectada.

        Cada categoría recibe lo que costaron **sus** renglones
        -`subtotal + impuesto`-, no el total de la compra: una compra
        desglosada en tres categorías contaría el triple si cada presupuesto
        se llevara el total. Varios renglones de la misma categoría se suman
        entre sí antes de tocar la fila, para leerla y escribirla una sola vez.

        El descuento global no se reparte entre categorías. La propuesta de
        dominio es explícita en que no se prorratea -se resta después de
        sumar, para que el titular vea de dónde salió la rebaja- así que lo
        que impacta a los presupuestos corresponde al total **antes** de ese
        descuento. Prorratearlo exigiría una regla de reparto que el dominio
        no define; asumir una acá sería inventarla.

        Como en la conciliación, un presupuesto en otra moneda que la compra
        no se toca: sumar colones sobre un límite en dólares daría un número
        inventado.
        """
        por_categoria: dict[int, Decimal] = {}
        for renglon in renglones:
            acumulado = por_categoria.get(renglon.categoria_id, Decimal("0"))
            por_categoria[renglon.categoria_id] = acumulado + renglon.subtotal + renglon.impuesto

        alertados: list[int] = []
        impactos: list[dict] = []
        for categoria_id, monto in por_categoria.items():
            presupuesto = self.presupuestos.buscar(
                comando.usuario_id, categoria_id, comando.fecha.year, comando.fecha.month
            )
            if presupuesto is None or presupuesto.moneda != comando.moneda:
                continue

            consumido_antes = presupuesto.monto_consumido
            porcentaje_antes, _ = PresupuestoService.calcular_estado(
                consumido_antes, presupuesto.monto_limite, presupuesto.umbral_alerta
            )
            presupuesto.monto_consumido = _redondear(consumido_antes + monto)
            _, estado_despues = PresupuestoService.calcular_estado(
                presupuesto.monto_consumido, presupuesto.monto_limite, presupuesto.umbral_alerta
            )
            # La alerta se dispara una sola vez: solo si antes de esta compra
            # el consumo estaba por debajo del umbral. Mismo criterio que la
            # conciliación -avisar en cada compra posterior sería ruido.
            if estado_despues != EstadoPresupuesto.EN_RANGO and porcentaje_antes < (
                presupuesto.umbral_alerta
            ):
                alertados.append(presupuesto.id)
            impactos.append(
                {
                    "presupuesto_id": presupuesto.id,
                    "categoria_id": categoria_id,
                    "consumido_antes": str(consumido_antes),
                    "consumido_despues": str(presupuesto.monto_consumido),
                }
            )
        return tuple(alertados), impactos

    def _escribir_bitacora(
        self,
        compra: Compra,
        renglones: list[_RenglonCalculado],
        lineas: tuple[LineaRegistrada, ...],
        impactos: list[dict],
        alertados: tuple[int, ...],
    ) -> None:
        """La trazabilidad, después de confirmar y sin poder hacer fallar nada.

        Mismo criterio que en la conciliación (ver ADR-002): la bitácora
        explica lo que pasó, no lo decide. El actor acá es el titular, no el
        servicio de ingesta -esta compra la capturó una persona.
        """
        actor = Actor(tipo="TITULAR", usuario_id=compra.usuario_id)

        def registrar(tipo: str, datos: dict) -> None:
            self.bitacora.registrar_evento(
                compra_id=compra.id,
                usuario_id=compra.usuario_id,
                estado_actual=compra.estado.value,
                tipo=tipo,
                datos=datos,
                actor=actor,
            )

        registrar(
            "DESGLOSE_MANUAL",
            {
                "renglones": len(lineas),
                "subtotal": str(compra.subtotal),
                "descuento": str(compra.descuento),
                "impuesto": str(compra.impuesto),
                "total": str(compra.total),
            },
        )
        automaticos = [
            {"linea_id": linea.linea_id, "categoria_id": linea.categoria_id,
             "origen": "REGLA" if renglon.regla else "COMERCIO",
             "regla_id": renglon.regla.id if renglon.regla else None}
            for linea, renglon in zip(lineas, renglones, strict=True)
            if linea.categorizada_automaticamente
        ]  # fmt: skip
        if automaticos:
            registrar("CATEGORIZACION_AUTOMATICA", {"renglones": automaticos})
        if compra.tipo_cambio_aplicado != Decimal("1"):
            registrar(
                "CONVERSION_MONEDA",
                {
                    "moneda_origen": compra.moneda.value,
                    "moneda_destino": MONEDA_BASE.value,
                    "tasa": str(compra.tipo_cambio_aplicado),
                    "monto_antes": str(compra.total),
                    "monto_despues": str(compra.total_moneda_base),
                },
            )
        registrar("CAMBIO_ESTADO", {"anterior": None, "nuevo": compra.estado.value})
        for impacto in impactos:
            registrar("IMPACTO_PRESUPUESTO", impacto)
        for presupuesto_id in alertados:
            registrar("ALERTA_PRESUPUESTO", {"presupuesto_id": presupuesto_id})

    def _asegurar_usuario_activo(self, usuario_id: int) -> None:
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        if not usuario.activo:
            raise UsuarioInactivo(f"El usuario {usuario_id} esta desactivado.")
