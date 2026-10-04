"""El Proceso 2 con dobles: cada camino de regla de `ConciliacionService`, sin base.

Todos los repositorios, el catálogo de comercios, el tipo de cambio y la
bitácora son dobles de `create_autospec`. Lo único real es el servicio y los
objetos de dominio que mueve -el `Comprobante`, la `Compra`- en memoria.

Con dobles se puede probar lo que contra una base cuesta provocar: que el
proveedor del tipo de cambio esté caído, o que una escritura falle justo en el
tercer intento.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, create_autospec

import pytest
from sqlalchemy.orm import Session

from app.business.errors import (
    CompraYaAnulada,
    CorreccionVacia,
    ErrorDeProveedorExterno,
    RecursoNoEncontrado,
    TransicionDeComprobanteInvalida,
)
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.comercio_service import ComercioService
from app.business.services.conciliacion_service import (
    ConciliacionService,
    ConciliarComprobanteComando,
)
from app.business.services.tipo_cambio_service import TipoCambioService, TipoDeCambio
from app.data.models.comercio import Comercio
from app.data.models.compra import Compra
from app.data.models.comprobante import Comprobante
from app.data.models.enums import (
    EstadoCompra,
    EstadoComprobante,
    Moneda,
    OrigenCompra,
    TipoMetodoPago,
)
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.models.presupuesto import Presupuesto
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.models.tipo_cambio import TipoCambio
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.comprobante_repository import ComprobanteRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.tipo_cambio_repository import TipoCambioRepository

USUARIO_ID = 1
COMPROBANTE_ID = 77
CATEGORIA_ID = 30
MONTO = Decimal("7870.00")
FECHA = datetime(2026, 8, 30, 13, 27)


@dataclass
class Dobles:
    """El servicio bajo prueba y cada uno de sus colaboradores, todos dobles."""

    servicio: ConciliacionService
    comprobante: Comprobante
    sesion: Mock
    compras: Mock
    lineas: Mock
    metodos_pago: Mock
    reglas: Mock
    presupuestos: Mock
    tipos_cambio: Mock
    comprobantes: Mock
    comercios: Mock
    tipo_cambio: Mock
    bitacora: Mock

    def no_se_creo_ninguna_compra(self) -> None:
        self.compras.agregar.assert_not_called()
        self.lineas.agregar.assert_not_called()
        self.bitacora.registrar_evento.assert_not_called()


@pytest.fixture
def dobles() -> Dobles:
    """El escenario base: un comprobante RECIBIDO del titular, sin tarjeta ni categoría."""
    sesion = create_autospec(Session, instance=True)

    def repositorio(clase):
        doble = create_autospec(clase, instance=True)
        doble.sesion = sesion
        return doble

    compras = repositorio(CompraRepository)
    lineas = repositorio(LineaCompraRepository)
    metodos_pago = repositorio(MetodoPagoRepository)
    reglas = repositorio(ReglaCategorizacionRepository)
    presupuestos = repositorio(PresupuestoRepository)
    categorias = repositorio(CategoriaRepository)
    sugerencias = repositorio(ComercioCategoriaRepository)
    tipos_cambio = repositorio(TipoCambioRepository)
    comprobantes = repositorio(ComprobanteRepository)
    comercios = create_autospec(ComercioService, instance=True)
    tipo_cambio = create_autospec(TipoCambioService, instance=True)
    bitacora = create_autospec(BitacoraComprasService, instance=True)

    comprobante = Comprobante(
        id=COMPROBANTE_ID,
        usuario_id=USUARIO_ID,
        cuenta_correo_id=1,
        mensaje_id="m-1",
        remitente="notificacion@baccredomatic.cr",
        banco="BAC Credomatic",
        confianza=0.0,
        estado=EstadoComprobante.RECIBIDO,
        intentos_procesamiento=0,
    )

    def con_id(entidad):
        entidad.id = 101
        return entidad

    compras.agregar.side_effect = con_id
    comprobantes.obtener_de_usuario.return_value = comprobante
    metodos_pago.buscar_por_ultimos_cuatro.return_value = None
    reglas.listar_activas_ordenadas.return_value = []
    presupuestos.buscar.return_value = None
    tipos_cambio.buscar.return_value = None
    comercios.resolver_o_crear.return_value = Comercio(
        id=7, nombre="WALMART SAN SEBASTIAN", nombre_normalizado="WALMART SAN SEBASTIAN"
    )
    comercios.categoria_sugerida_para.return_value = None

    servicio = ConciliacionService(
        compras, lineas, metodos_pago, reglas, presupuestos, categorias, sugerencias,
        tipos_cambio, comprobantes, comercios, tipo_cambio, bitacora,
    )  # fmt: skip
    return Dobles(
        servicio, comprobante, sesion, compras, lineas, metodos_pago, reglas, presupuestos,
        tipos_cambio, comprobantes, comercios, tipo_cambio, bitacora,
    )  # fmt: skip


def _comando(**cambios) -> ConciliarComprobanteComando:
    datos = dict(
        usuario_id=USUARIO_ID,
        comprobante_id=COMPROBANTE_ID,
        comercio="WALMART SAN SEBASTIAN",
        monto=MONTO,
        moneda="CRC",
        fecha=FECHA,
        ultimos_cuatro="4321",
        confianza=1.0,
    )
    return ConciliarComprobanteComando(**{**datos, **cambios})


def _con_tarjeta_y_categoria(dobles: Dobles) -> None:
    dobles.metodos_pago.buscar_por_ultimos_cuatro.return_value = MetodoPago(
        id=5, usuario_id=USUARIO_ID, alias="Visa BAC", tipo=TipoMetodoPago.CREDITO, activo=True
    )
    dobles.comercios.categoria_sugerida_para.return_value = CATEGORIA_ID


# ---- la entrada: un comando, no una entidad ----


def test_el_comprobante_se_busca_por_id_y_por_titular(dobles: Dobles) -> None:
    """El servicio no recibe la entidad: la busca, y la busca con su dueño."""
    dobles.servicio.conciliar(_comando())

    dobles.comprobantes.obtener_de_usuario.assert_called_with(COMPROBANTE_ID, USUARIO_ID)


def test_un_comprobante_ajeno_es_como_si_no_existiera(dobles: Dobles) -> None:
    dobles.comprobantes.obtener_de_usuario.return_value = None

    with pytest.raises(RecursoNoEncontrado):
        dobles.servicio.conciliar(_comando())

    dobles.no_se_creo_ninguna_compra()
    dobles.sesion.commit.assert_not_called()


# ---- cuándo no se convierte en compra ----


@pytest.mark.parametrize(
    "cambios, motivo",
    [
        ({"confianza": 0.5}, "0.75"),
        ({"tipo_transaccion": "ANULACION"}, "no es una compra"),
        ({"comercio": None}, "comercio"),
        ({"monto": None}, "monto"),
        ({"fecha": None}, "fecha"),
        ({"moneda": "XYZ"}, "moneda"),
    ],
)
def test_lo_que_no_alcanza_para_conciliar_queda_en_revision_manual(
    dobles: Dobles, cambios: dict, motivo: str
) -> None:
    resultado = dobles.servicio.conciliar(_comando(**cambios))

    assert resultado.estado == EstadoComprobante.REVISION_MANUAL
    assert resultado.compra_id is None
    assert motivo in resultado.motivo
    dobles.no_se_creo_ninguna_compra()
    dobles.comercios.resolver_o_crear.assert_not_called()


@pytest.mark.parametrize("estado", [EstadoComprobante.PROCESADO, EstadoComprobante.FALLIDO])
def test_un_comprobante_en_estado_terminal_no_se_concilia(
    dobles: Dobles, estado: EstadoComprobante
) -> None:
    dobles.comprobante.estado = estado

    with pytest.raises(TransicionDeComprobanteInvalida):
        dobles.servicio.conciliar(_comando())

    dobles.no_se_creo_ninguna_compra()


# ---- el camino feliz ----


def test_concilia_y_deja_el_comprobante_procesado_en_un_solo_commit(dobles: Dobles) -> None:
    _con_tarjeta_y_categoria(dobles)

    resultado = dobles.servicio.conciliar(_comando())

    assert resultado.estado == EstadoComprobante.PROCESADO
    assert resultado.compra_id == 101
    assert resultado.requiere_revision is False
    assert dobles.comprobante.compra_id == 101

    compra = dobles.compras.agregar.call_args.args[0]
    assert compra.origen == OrigenCompra.INGESTA_CORREO
    assert compra.total == compra.total_moneda_base == MONTO
    assert compra.fecha == date(2026, 8, 30)
    assert compra.impuesto_desglosado is False, "el total del banco ya trae el impuesto adentro"
    linea = dobles.lineas.agregar.call_args.args[0]
    assert (linea.compra_id, linea.usuario_id, linea.categoria_id) == (101, USUARIO_ID, 30)
    assert linea.categorizada_automaticamente is True
    # Dos commits: cerrar el parseo (RECIBIDO → PARSEADO) y la transacción de la compra.
    assert dobles.sesion.commit.call_count == 2
    dobles.sesion.rollback.assert_not_called()


def test_la_tarjeta_se_empareja_por_titular_y_ultimos_cuatro(dobles: Dobles) -> None:
    dobles.servicio.conciliar(_comando())

    dobles.metodos_pago.buscar_por_ultimos_cuatro.assert_called_once_with(USUARIO_ID, "4321")


def test_sin_tarjeta_conocida_la_compra_se_crea_marcada_para_revision(dobles: Dobles) -> None:
    dobles.comercios.categoria_sugerida_para.return_value = CATEGORIA_ID

    resultado = dobles.servicio.conciliar(_comando())

    assert resultado.requiere_revision is True
    assert dobles.compras.agregar.call_args.args[0].metodo_pago_id is None


def test_sin_categoria_la_compra_se_crea_marcada_para_revision(dobles: Dobles) -> None:
    resultado = dobles.servicio.conciliar(_comando())

    assert resultado.estado == EstadoComprobante.PROCESADO
    assert resultado.requiere_revision is True
    linea = dobles.lineas.agregar.call_args.args[0]
    assert linea.categoria_id is None
    assert linea.categorizada_automaticamente is False
    dobles.presupuestos.buscar.assert_not_called()


def test_una_regla_gana_sobre_la_sugerencia_del_comercio_y_suma_su_contador(
    dobles: Dobles,
) -> None:
    regla = ReglaCategorizacion(
        id=9, usuario_id=USUARIO_ID, categoria_destino_id=40, nombre="Walmart",
        patron="WALMART", prioridad=1, activa=True, veces_aplicada=2,
    )  # fmt: skip
    dobles.reglas.listar_activas_ordenadas.return_value = [regla]
    dobles.comercios.categoria_sugerida_para.return_value = CATEGORIA_ID

    dobles.servicio.conciliar(_comando())

    assert dobles.lineas.agregar.call_args.args[0].categoria_id == 40
    assert regla.veces_aplicada == 3
    dobles.comercios.categoria_sugerida_para.assert_not_called()


# ---- tipo de cambio ----


def test_en_colones_ni_se_pregunta_por_el_tipo_de_cambio(dobles: Dobles) -> None:
    dobles.servicio.conciliar(_comando())

    dobles.tipos_cambio.buscar.assert_not_called()
    dobles.tipo_cambio.obtener.assert_not_called()


def test_con_el_proveedor_caido_el_comprobante_queda_pendiente(dobles: Dobles) -> None:
    """La regla de la propuesta: no se inventa una tasa. Antes se usaba 1."""
    dobles.tipo_cambio.obtener.side_effect = ErrorDeProveedorExterno("BCCR no responde")

    resultado = dobles.servicio.conciliar(_comando(moneda="USD", monto=Decimal("10.00")))

    assert resultado.estado == EstadoComprobante.PARSEADO
    assert resultado.compra_id is None
    assert "tipo de cambio" in resultado.motivo
    assert dobles.comprobante.intentos_procesamiento == 0, "esperar la tasa no es un fallo"
    dobles.no_se_creo_ninguna_compra()
    dobles.tipos_cambio.guardar_tasa.assert_not_called()


def test_sin_servicio_de_tipo_de_cambio_tambien_queda_pendiente(dobles: Dobles) -> None:
    dobles.servicio.tipo_cambio_servicio = None

    resultado = dobles.servicio.conciliar(_comando(moneda="USD", monto=Decimal("10.00")))

    assert resultado.estado == EstadoComprobante.PARSEADO
    dobles.no_se_creo_ninguna_compra()


def test_la_tasa_del_historico_propio_gana_y_no_se_le_pregunta_al_proveedor(
    dobles: Dobles,
) -> None:
    dobles.tipos_cambio.buscar.return_value = TipoCambio(tasa=Decimal("540"))

    dobles.servicio.conciliar(_comando(moneda="USD", monto=Decimal("10.00")))

    dobles.tipos_cambio.buscar.assert_called_once_with(Moneda.USD, Moneda.CRC, date(2026, 8, 30))
    dobles.tipo_cambio.obtener.assert_not_called()
    compra = dobles.compras.agregar.call_args.args[0]
    assert compra.tipo_cambio_aplicado == Decimal("540")
    assert compra.total_moneda_base == Decimal("5400.00")


def test_la_tasa_del_proveedor_se_usa_y_se_guarda_como_historico(dobles: Dobles) -> None:
    dobles.tipo_cambio.obtener.return_value = TipoDeCambio(
        fecha=date(2026, 8, 30), compra=Decimal("545"), venta=Decimal("550")
    )

    dobles.servicio.conciliar(_comando(moneda="USD", monto=Decimal("10.00")))

    compra = dobles.compras.agregar.call_args.args[0]
    assert compra.total_moneda_base == Decimal("5500.00"), "con la tasa de venta"
    dobles.tipos_cambio.guardar_tasa.assert_called_once_with(
        moneda_origen=Moneda.USD,
        moneda_destino=Moneda.CRC,
        fecha=date(2026, 8, 30),
        tasa=Decimal("550"),
        fuente="BCCR",
    )


# ---- presupuesto ----


def _presupuesto(consumido: str, moneda: Moneda = Moneda.CRC) -> Presupuesto:
    return Presupuesto(
        id=40, usuario_id=USUARIO_ID, categoria_id=CATEGORIA_ID, anio=2026, mes=8,
        moneda=moneda, monto_limite=Decimal("10000.00"), monto_consumido=Decimal(consumido),
        umbral_alerta=80,
    )  # fmt: skip


def test_acumula_el_presupuesto_y_avisa_al_cruzar_el_umbral(dobles: Dobles) -> None:
    _con_tarjeta_y_categoria(dobles)
    presupuesto = _presupuesto("1000.00")
    dobles.presupuestos.buscar.return_value = presupuesto

    resultado = dobles.servicio.conciliar(_comando())

    dobles.presupuestos.buscar.assert_called_once_with(USUARIO_ID, CATEGORIA_ID, 2026, 8)
    assert presupuesto.monto_consumido == Decimal("8870.00")
    assert resultado.presupuesto_alertado is True, "1000 + 7870 = 88.7 % de 10000"


def test_no_vuelve_a_avisar_si_ya_estaba_sobre_el_umbral(dobles: Dobles) -> None:
    _con_tarjeta_y_categoria(dobles)
    dobles.presupuestos.buscar.return_value = _presupuesto("9000.00")

    assert dobles.servicio.conciliar(_comando()).presupuesto_alertado is False


def test_un_presupuesto_en_otra_moneda_no_se_toca(dobles: Dobles) -> None:
    _con_tarjeta_y_categoria(dobles)
    presupuesto = _presupuesto("1000.00", moneda=Moneda.USD)
    dobles.presupuestos.buscar.return_value = presupuesto

    resultado = dobles.servicio.conciliar(_comando())

    assert presupuesto.monto_consumido == Decimal("1000.00")
    assert resultado.presupuesto_alertado is False


# ---- la transacción y los tres intentos ----


def test_si_una_escritura_falla_se_revierte_y_se_cuenta_el_intento(dobles: Dobles) -> None:
    dobles.lineas.agregar.side_effect = RuntimeError("se cayó la base")

    with pytest.raises(RuntimeError):
        dobles.servicio.conciliar(_comando())

    dobles.sesion.rollback.assert_called_once_with()
    assert dobles.comprobante.estado == EstadoComprobante.PARSEADO, "se puede reintentar"
    assert dobles.comprobante.intentos_procesamiento == 1
    assert "se cayó la base" in dobles.comprobante.motivo_fallo
    dobles.bitacora.registrar_evento.assert_not_called()


def test_el_rollback_ocurre_antes_de_contar_el_intento(dobles: Dobles) -> None:
    """Si el intento se contara dentro de la transacción que falló, se revertiría con ella."""
    dobles.lineas.agregar.side_effect = RuntimeError("se cayó la base")
    intentos_al_revertir = []
    dobles.sesion.rollback.side_effect = lambda: intentos_al_revertir.append(
        dobles.comprobante.intentos_procesamiento
    )

    with pytest.raises(RuntimeError):
        dobles.servicio.conciliar(_comando())

    assert intentos_al_revertir == [0]
    assert dobles.comprobante.intentos_procesamiento == 1


def test_al_tercer_fallo_el_comprobante_pasa_a_fallido(dobles: Dobles) -> None:
    dobles.lineas.agregar.side_effect = RuntimeError("se cayó la base")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            dobles.servicio.conciliar(_comando())

    assert dobles.comprobante.estado == EstadoComprobante.FALLIDO
    assert dobles.comprobante.intentos_procesamiento == 3
    with pytest.raises(TransicionDeComprobanteInvalida):
        dobles.servicio.conciliar(_comando())
    assert dobles.compras.agregar.call_count == 3, "el cuarto intento ni llega a escribir"


# ---- anulación ----


def _compra(**cambios) -> Compra:
    datos = dict(
        id=101, usuario_id=USUARIO_ID, comercio_id=7, fecha=date(2026, 8, 30), moneda=Moneda.CRC,
        estado=EstadoCompra.REGISTRADA, total=Decimal("2260.00"), impuesto_desglosado=True,
        requiere_revision=True,
    )  # fmt: skip
    return Compra(**{**datos, **cambios})


def test_anular_devuelve_a_cada_presupuesto_lo_que_sus_renglones_le_sumaron(
    dobles: Dobles,
) -> None:
    """Con desglose cada renglón había sumado `subtotal + impuesto`; el exento, el subtotal."""
    compra = _compra()
    dobles.compras.obtener_de_usuario.return_value = compra
    dobles.lineas.listar_de_compra.return_value = [
        LineaCompra(categoria_id=30, subtotal=Decimal("1000.00"), exento_impuesto=False),
        LineaCompra(categoria_id=30, subtotal=Decimal("500.00"), exento_impuesto=True),
        LineaCompra(categoria_id=None, subtotal=Decimal("999.00"), exento_impuesto=False),
    ]
    presupuesto = _presupuesto("5000.00")
    dobles.presupuestos.buscar.return_value = presupuesto

    anulada = dobles.servicio.anular(USUARIO_ID, 101)

    dobles.compras.obtener_de_usuario.assert_called_once_with(101, USUARIO_ID)
    assert presupuesto.monto_consumido == Decimal("3370.00"), "5000 − (1130 + 500)"
    assert anulada.estado == compra.estado == EstadoCompra.ANULADA
    assert anulada.presupuestos_devueltos == (40,)
    assert compra.requiere_revision is False
    dobles.sesion.commit.assert_called_once_with()


def test_el_consumido_nunca_queda_negativo(dobles: Dobles) -> None:
    dobles.compras.obtener_de_usuario.return_value = _compra(impuesto_desglosado=False)
    dobles.lineas.listar_de_compra.return_value = [
        LineaCompra(categoria_id=30, subtotal=Decimal("7870.00"), exento_impuesto=False)
    ]
    presupuesto = _presupuesto("100.00")
    dobles.presupuestos.buscar.return_value = presupuesto

    dobles.servicio.anular(USUARIO_ID, 101)

    assert presupuesto.monto_consumido == Decimal("0")


def test_una_compra_ya_anulada_no_se_anula_de_nuevo(dobles: Dobles) -> None:
    dobles.compras.obtener_de_usuario.return_value = _compra(estado=EstadoCompra.ANULADA)

    with pytest.raises(CompraYaAnulada):
        dobles.servicio.anular(USUARIO_ID, 101)

    dobles.presupuestos.buscar.assert_not_called()
    dobles.sesion.commit.assert_not_called()


def test_anular_una_compra_ajena_es_como_si_no_existiera(dobles: Dobles) -> None:
    dobles.compras.obtener_de_usuario.return_value = None

    with pytest.raises(RecursoNoEncontrado):
        dobles.servicio.anular(USUARIO_ID, 101)

    dobles.sesion.commit.assert_not_called()


# ---- corrección manual ----


def test_corregir_nada_no_es_una_correccion(dobles: Dobles) -> None:
    with pytest.raises(CorreccionVacia):
        dobles.servicio.resolver_revision(USUARIO_ID, 101, None, None)

    dobles.compras.obtener_de_usuario.assert_not_called()


def test_una_compra_anulada_no_se_corrige(dobles: Dobles) -> None:
    dobles.compras.obtener_de_usuario.return_value = _compra(estado=EstadoCompra.ANULADA)

    with pytest.raises(CompraYaAnulada):
        dobles.servicio.resolver_revision(USUARIO_ID, 101, 5, None)

    dobles.sesion.commit.assert_not_called()
