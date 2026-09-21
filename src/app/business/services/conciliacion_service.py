"""Conciliación transaccional de un comprobante en una Compra real de negocio.

Implementa los pasos 4-9 del Proceso 2 del dominio (ver
docs/propuesta-dominio.md): emparejar método de pago, resolver comercio,
categorizar, crear la `Compra` y su línea, acumular el presupuesto, y dejar
el comprobante ligado a su compra. Los pasos 1-3 -leer el correo, guardar el
`Comprobante`, parsearlo- ya los hace
`CuentaCorreoService._sincronizar_comprobantes` antes de llamar acá.

**Es aditivo, no reemplaza nada.** `Comprobante` conserva todas sus columnas
de siempre (banco, comercio, monto...) y sigue alimentando Resumen,
Comercios, Presupuestos "de antes" y los reportes exportables tal cual; solo
gana un `compra_id` que apunta a la `Compra` real que esta conciliación creó.

Todo lo que este método escribe en PostgreSQL -`Compra`, `LineaCompra`, el
contador de la regla que acertó, `Presupuesto.monto_consumido`,
`Comprobante.compra_id`- queda en una sola transacción: si algo falla a
mitad de camino, se revierte todo -nunca queda un comprobante marcado como
conciliado sin que su gasto se haya sumado al presupuesto. La resolución del
`Comercio` (`ComercioService.resolver_o_crear`) confirma aparte, con su
propio commit: es un catálogo compartido entre titulares, y su creación no
es parte de la conciliación de uno en particular -en el Proceso 2 del
dominio, "se resuelve el Comercio" es un paso previo a "se crea la Compra".

La bitácora de Mongo se escribe **después** de confirmar en PostgreSQL, y
nunca puede hacer fallar la conciliación -ver `BitacoraComprasService`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.business.errors import (
    DatosInvalidos,
    ErrorDeProveedorExterno,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
)
from app.business.parsers.comprobante_bac import ComprobanteParseado
from app.business.services.bitacora_service import Actor, BitacoraComprasService
from app.business.services.categorizacion import primera_regla_que_coincide
from app.business.services.comercio_service import ComercioService
from app.business.services.presupuesto_service import PresupuestoService
from app.business.services.tipo_cambio_service import TipoCambioService
from app.data.models.compra import Compra
from app.data.models.comprobante import Comprobante
from app.data.models.enums import EstadoCompra, EstadoPresupuesto, Moneda, OrigenCompra
from app.data.models.linea_compra import LineaCompra
from app.data.models.regla_categorizacion import ReglaCategorizacion
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


@dataclass(frozen=True)
class ResultadoConciliacion:
    """Lo que produjo conciliar un comprobante."""

    compra_id: int
    requiere_revision: bool
    presupuesto_alertado: bool


class ConciliacionService:
    """Aplica el Proceso 2 del dominio sobre un comprobante ya parseado."""

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

    def conciliar(
        self, usuario_id: int, comprobante: Comprobante, parseado: ComprobanteParseado
    ) -> ResultadoConciliacion | None:
        """Corre los pasos 4-9 del Proceso 2. `None` si el comprobante no alcanza
        para conciliar solo -queda para revisión manual, no se inventa nada."""
        if not (
            parseado.es_compra
            and parseado.es_confiable
            and parseado.comercio
            and parseado.monto is not None
            and parseado.moneda
            and parseado.fecha is not None
        ):
            return None

        # Paso 4: emparejar método de pago -nunca se crea uno solo, ver MetodoPago.
        metodo_pago = None
        if parseado.ultimos_cuatro:
            metodo_pago = self.metodos_pago.buscar_por_ultimos_cuatro(
                usuario_id, parseado.ultimos_cuatro
            )

        # Paso 5: resolver el comercio (catálogo compartido, confirma con su propio commit).
        comercio = self.comercios_servicio.resolver_o_crear(parseado.comercio)

        # Paso 6 (categorización): regla activa por prioridad, si no hay,
        # la sugerencia que este titular ya le puso a este comercio.
        categoria_id, regla_aplicada = self._categorizar(usuario_id, comercio.nombre_normalizado)
        if categoria_id is None:
            categoria_id = self.comercios_servicio.categoria_sugerida_para(usuario_id, comercio.id)

        moneda = Moneda(parseado.moneda) if parseado.moneda in Moneda.__members__ else None
        if moneda is None:
            return None  # una moneda que el sistema no reconoce no se inventa a qué tasa vale

        total = parseado.monto
        tipo_cambio_aplicado = Decimal("1")
        if moneda != _MONEDA_BASE:
            tipo_cambio_aplicado = self._tasa_de_conversion(moneda, parseado.fecha.date())
        total_moneda_base = (total * tipo_cambio_aplicado).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        requiere_revision = metodo_pago is None or categoria_id is None

        compra = Compra(
            usuario_id=usuario_id,
            comercio_id=comercio.id,
            metodo_pago_id=metodo_pago.id if metodo_pago else None,
            fecha=parseado.fecha.date(),
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
            total_moneda_base=total_moneda_base,
            requiere_revision=requiere_revision,
        )
        self.compras.agregar(compra)  # flush: ya tiene compra.id de acá en adelante

        self.lineas.agregar(
            LineaCompra(
                compra_id=compra.id,
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

        if regla_aplicada is not None:
            regla_aplicada.veces_aplicada += 1

        alerta_presupuesto = False
        presupuesto = None
        consumido_antes = consumido_despues = None
        if categoria_id is not None:
            presupuesto = self.presupuestos.buscar(
                usuario_id, categoria_id, compra.fecha.year, compra.fecha.month
            )
            # Solo se acumula si el presupuesto está en la MISMA moneda que la
            # compra -mezclar monedas en una suma daría un número inventado.
            if presupuesto is not None and presupuesto.moneda == moneda:
                consumido_antes = presupuesto.monto_consumido
                porcentaje_antes, _ = PresupuestoService.calcular_estado(
                    consumido_antes, presupuesto.monto_limite, presupuesto.umbral_alerta
                )
                presupuesto.monto_consumido = presupuesto.monto_consumido + total
                consumido_despues = presupuesto.monto_consumido
                porcentaje_despues, estado_despues = PresupuestoService.calcular_estado(
                    consumido_despues, presupuesto.monto_limite, presupuesto.umbral_alerta
                )
                alerta_presupuesto = (
                    estado_despues != EstadoPresupuesto.EN_RANGO
                    and porcentaje_antes < presupuesto.umbral_alerta
                )

        comprobante.compra_id = compra.id

        # Un solo commit: todo lo de arriba, o nada.
        self.comprobantes.sesion.commit()

        self._escribir_bitacora(
            compra=compra,
            usuario_id=usuario_id,
            parseado=parseado,
            metodo_pago_id=metodo_pago.id if metodo_pago else None,
            comercio_nombre=comercio.nombre,
            comercio_normalizado=comercio.nombre_normalizado,
            categoria_id=categoria_id,
            regla_aplicada=regla_aplicada,
            tipo_cambio_aplicado=tipo_cambio_aplicado,
            requiere_revision=requiere_revision,
            presupuesto_id=presupuesto.id if presupuesto else None,
            consumido_antes=consumido_antes,
            consumido_despues=consumido_despues,
            alerta_presupuesto=alerta_presupuesto,
        )

        return ResultadoConciliacion(
            compra_id=compra.id,
            requiere_revision=requiere_revision,
            presupuesto_alertado=alerta_presupuesto,
        )

    def recategorizar_compras_de_comercio(
        self, usuario_id: int, comercio_id: int, categoria_id: int
    ) -> int:
        """Aplica una categoría recién asignada a un comercio sobre las compras que
        ya se conciliaron sin categoría -"corregir crea la regla" también corrige
        lo que ya pasó, no solo lo que viene.

        Se llama después de `ComercioService.asignar_categoria`, desde el mismo
        endpoint. Solo toca renglones sin categoría -una compra que sí tenía
        una (una regla la puso, o una corrección anterior) no se pisa sola.
        Devuelve cuántas compras se corrigieron.
        """
        afectadas = self.lineas.listar_sin_categoria_de_comercio(usuario_id, comercio_id)
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
    ) -> Compra:
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
        """
        if metodo_pago_id is None and categoria_id is None:
            raise DatosInvalidos("Hay que corregir al menos el método de pago o la categoría.")

        compra = self.compras.obtener_de_usuario(compra_id, usuario_id)
        if compra is None:
            raise RecursoNoEncontrado(f"La compra {compra_id} no existe en esta cuenta.")

        actor = Actor(tipo="TITULAR", usuario_id=usuario_id)
        metodo_pago_anterior_id = compra.metodo_pago_id

        if metodo_pago_id is not None:
            metodo_pago = self.metodos_pago.obtener_de_usuario(metodo_pago_id, usuario_id)
            if metodo_pago is None:
                raise RecursoNoEncontrado(
                    f"El método de pago {metodo_pago_id} no existe en esta cuenta."
                )
            if not metodo_pago.activo:
                raise ReglaDeNegocioViolada("Ese método de pago está desactivado.")
            # Por la relación, no por la columna: `compra` ya llegó con
            # `metodo_pago` cargado (la trae `CompraRepository.obtener_de_usuario`
            # con joinedload), y asignar solo `metodo_pago_id` dejaría ese
            # atributo desactualizado -la siguiente lectura en esta misma
            # sesión seguiría viendo el método de pago viejo.
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
                raise ReglaDeNegocioViolada("La categoría tiene que ser una hoja, no un grupo.")
            if linea_principal is None:
                raise ReglaDeNegocioViolada("Esta compra no tiene ningún renglón que categorizar.")
            # Por la relación, no por la columna -mismo motivo que
            # `compra.metodo_pago` unas líneas arriba: `linea_principal` ya
            # llegó con `categoria` cargada (vía `compra.lineas` en
            # `obtener_de_usuario`).
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

        self.bitacora.registrar_evento(
            compra_id=compra.id,
            usuario_id=usuario_id,
            estado_actual=compra.estado.value,
            tipo="CORRECCION_MANUAL",
            datos={
                "metodo_pago_anterior_id": metodo_pago_anterior_id,
                "metodo_pago_nuevo_id": compra.metodo_pago_id,
                "categoria_anterior_id": categoria_anterior_id,
                "categoria_nueva_id": linea_principal.categoria_id if linea_principal else None,
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

        return compra

    def _categorizar(
        self, usuario_id: int, comercio_normalizado: str
    ) -> tuple[int | None, ReglaCategorizacion | None]:
        """Primera regla activa (prioridad ascendente) cuyo patrón está contenido en el
        nombre normalizado del comercio. `None` si ninguna coincide -cae a la
        sugerencia del comercio, resuelta por quien llama.

        La decisión en sí vive en `categorizacion.primera_regla_que_coincide`,
        compartida con el registro manual: los dos procesos tienen que
        categorizar igual."""
        regla = primera_regla_que_coincide(
            self.reglas.listar_activas_ordenadas(usuario_id), comercio_normalizado
        )
        return (regla.categoria_destino_id, regla) if regla is not None else (None, None)

    def _tasa_de_conversion(self, moneda: Moneda, fecha: date) -> Decimal:
        """La tasa aplicada a esta compra, guardada como histórico real -no la caché
        en memoria de `TipoCambioService`. Si el servicio de moneda no está
        disponible, se usa 1 -mejor un total sin convertir de más que perder el
        gasto por completo (mismo criterio que `CuentaCorreoService._tipo_de_cambio_de_hoy`)."""
        if self.tipo_cambio_servicio is None:
            return Decimal("1")
        try:
            tipo_de_cambio = self.tipo_cambio_servicio.obtener(fecha)
        except ErrorDeProveedorExterno:
            return Decimal("1")
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
        compra: Compra,
        usuario_id: int,
        parseado: ComprobanteParseado,
        metodo_pago_id: int | None,
        comercio_nombre: str,
        comercio_normalizado: str,
        categoria_id: int | None,
        regla_aplicada: ReglaCategorizacion | None,
        tipo_cambio_aplicado: Decimal,
        requiere_revision: bool,
        presupuesto_id: int | None,
        consumido_antes: Decimal | None,
        consumido_despues: Decimal | None,
        alerta_presupuesto: bool,
    ) -> None:
        actor = Actor(tipo="SERVICIO", nombre="ingesta-correo")

        def registrar(tipo: str, datos: dict) -> None:
            self.bitacora.registrar_evento(
                compra_id=compra.id,
                usuario_id=usuario_id,
                estado_actual=compra.estado.value,
                tipo=tipo,
                datos=datos,
                actor=actor,
            )

        registrar(
            "PARSEO_COMPROBANTE",
            {
                "confianza": parseado.confianza,
                "campos_extraidos": [
                    campo
                    for campo in ("comercio", "monto", "moneda", "fecha", "ultimos_cuatro")
                    if getattr(parseado, campo, None) is not None
                ],
            },
        )
        registrar(
            "EMPAREJAMIENTO_METODO_PAGO",
            {
                "ultimos_cuatro": parseado.ultimos_cuatro,
                "resultado": "EMPAREJADO" if metodo_pago_id else "SIN_COINCIDENCIA",
                "metodo_pago_id": metodo_pago_id,
            },
        )
        registrar(
            "RESOLUCION_COMERCIO",
            {
                "nombre_crudo": parseado.comercio,
                "nombre_normalizado": comercio_normalizado,
                "comercio_id": compra.comercio_id,
            },
        )
        registrar(
            "CATEGORIZACION_AUTOMATICA",
            {
                "origen": "REGLA" if regla_aplicada else ("COMERCIO" if categoria_id else None),
                "regla_id": regla_aplicada.id if regla_aplicada else None,
                "categoria_id": categoria_id,
            },
        )
        if tipo_cambio_aplicado != Decimal("1"):
            registrar(
                "CONVERSION_MONEDA",
                {
                    "moneda_origen": compra.moneda.value,
                    "moneda_destino": _MONEDA_BASE.value,
                    "tasa": str(tipo_cambio_aplicado),
                    "monto_antes": str(compra.total),
                    "monto_despues": str(compra.total_moneda_base),
                },
            )
        registrar(
            "CAMBIO_ESTADO",
            {"anterior": None, "nuevo": compra.estado.value},
        )
        if presupuesto_id is not None and consumido_antes is not None:
            registrar(
                "IMPACTO_PRESUPUESTO",
                {
                    "presupuesto_id": presupuesto_id,
                    "consumido_antes": str(consumido_antes),
                    "consumido_despues": str(consumido_despues),
                },
            )
        if alerta_presupuesto:
            registrar("ALERTA_PRESUPUESTO", {"presupuesto_id": presupuesto_id})
        if requiere_revision:
            registrar(
                "REVISION_REQUERIDA",
                {
                    "motivo": "SIN_METODO_DE_PAGO" if metodo_pago_id is None else "SIN_CATEGORIA",
                },
            )
