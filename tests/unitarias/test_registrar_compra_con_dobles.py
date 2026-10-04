"""El Proceso 1 con dobles: cada camino de regla de `RegistrarCompraService`, sin base.

Los repositorios son dobles de `create_autospec`. Eso permite verificar dos
cosas que una prueba contra la base no deja ver con claridad:

- **Qué le preguntó el servicio a sus colaboradores** -por ejemplo, que la
  categoría se busque por id *y por titular*, que es la verificación de
  propiedad.
- **Que una regla rota corta antes de escribir**: ni un `agregar`, ni un
  `commit`.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock, create_autospec

import pytest
from sqlalchemy.orm import Session

from app.business.errors import (
    CategoriaInactiva,
    CategoriaNoEsHoja,
    CompraSinRenglones,
    CuadreFueraDeTolerancia,
    DescuentoExcedido,
    FechaFutura,
    MetodoPagoInactivo,
    RecursoNoEncontrado,
    RenglonSinCategoria,
    TipoDeCambioRequerido,
    UsuarioInactivo,
)
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.comercio_service import ComercioService
from app.business.services.registrar_compra_service import (
    LineaDeCompraComando,
    RegistrarCompraComando,
    RegistrarCompraService,
)
from app.data.models.categoria import Categoria
from app.data.models.comercio import Comercio
from app.data.models.enums import EstadoCompra, Moneda, TipoMetodoPago
from app.data.models.metodo_pago import MetodoPago
from app.data.models.presupuesto import Presupuesto
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.models.usuario import Usuario
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.usuario_repository import UsuarioRepository

USUARIO_ID = 1
COMERCIO_ID = 7
CATEGORIA_ID = 30
FECHA = date(2026, 8, 30)


@dataclass
class Dobles:
    """El servicio bajo prueba y cada uno de sus colaboradores, todos dobles."""

    servicio: RegistrarCompraService
    sesion: Mock
    compras: Mock
    lineas: Mock
    categorias: Mock
    metodos_pago: Mock
    presupuestos: Mock
    reglas: Mock
    usuarios: Mock
    comercios: Mock
    bitacora: Mock

    def nada_se_escribio(self) -> None:
        self.compras.agregar.assert_not_called()
        self.lineas.agregar.assert_not_called()
        self.sesion.commit.assert_not_called()
        self.bitacora.registrar_evento.assert_not_called()


def _categoria(identificador: int = CATEGORIA_ID, **cambios) -> Categoria:
    datos = dict(
        id=identificador, usuario_id=USUARIO_ID, nombre="Supermercado", es_hoja=True, activa=True
    )
    return Categoria(**{**datos, **cambios})


@pytest.fixture
def dobles() -> Dobles:
    """El escenario feliz: titular activo, comercio existente, una categoría hoja."""
    sesion = create_autospec(Session, instance=True)

    def repositorio(clase):
        doble = create_autospec(clase, instance=True)
        doble.sesion = sesion
        return doble

    compras = repositorio(CompraRepository)
    lineas = repositorio(LineaCompraRepository)
    categorias = repositorio(CategoriaRepository)
    metodos_pago = repositorio(MetodoPagoRepository)
    presupuestos = repositorio(PresupuestoRepository)
    reglas = repositorio(ReglaCategorizacionRepository)
    usuarios = repositorio(UsuarioRepository)
    comercios = create_autospec(ComercioService, instance=True)
    bitacora = create_autospec(BitacoraComprasService, instance=True)

    # El `flush` de la base es lo que le pone el id a una entidad nueva; acá lo
    # simula el doble.
    def con_id(identificador: int):
        def _agregar(entidad):
            entidad.id = identificador
            return entidad

        return _agregar

    compras.agregar.side_effect = con_id(101)
    lineas.agregar.side_effect = con_id(501)
    usuarios.obtener_por_id.return_value = Usuario(id=USUARIO_ID, activo=True)
    comercios.obtener.return_value = Comercio(
        id=COMERCIO_ID, nombre="Walmart San Sebastián", nombre_normalizado="WALMART SAN SEBASTIAN"
    )
    comercios.categoria_sugerida_para.return_value = None
    categorias.obtener_de_usuario.return_value = _categoria()
    reglas.listar_activas_ordenadas.return_value = []
    presupuestos.buscar.return_value = None

    servicio = RegistrarCompraService(
        compras, lineas, categorias, metodos_pago, presupuestos, reglas, usuarios, comercios,
        bitacora,
    )  # fmt: skip
    return Dobles(
        servicio, sesion, compras, lineas, categorias, metodos_pago, presupuestos, reglas,
        usuarios, comercios, bitacora,
    )  # fmt: skip


def _comando(**cambios) -> RegistrarCompraComando:
    datos = dict(
        usuario_id=USUARIO_ID,
        comercio_id=COMERCIO_ID,
        fecha=FECHA,
        lineas=(
            LineaDeCompraComando(
                descripcion="Leche 1L",
                cantidad=Decimal("2"),
                precio_unitario=Decimal("1000.00"),
                categoria_id=CATEGORIA_ID,
            ),
        ),
    )
    return RegistrarCompraComando(**{**datos, **cambios})


def _linea(**cambios) -> LineaDeCompraComando:
    datos = dict(descripcion="Leche 1L", cantidad=Decimal("2"), precio_unitario=Decimal("1000.00"))
    return LineaDeCompraComando(**{**datos, **cambios})


# ---- el camino feliz ----


def test_calcula_los_totales_y_escribe_todo_en_un_solo_commit(dobles: Dobles) -> None:
    registrada = dobles.servicio.registrar(_comando())

    assert registrada.compra_id == 101
    assert registrada.subtotal == Decimal("2000.00")
    assert registrada.impuesto == Decimal("260.00"), "13 % de IVA sobre el subtotal"
    assert registrada.total == Decimal("2260.00")
    assert registrada.estado == EstadoCompra.REGISTRADA
    assert registrada.lineas[0].linea_id == 501

    compra = dobles.compras.agregar.call_args.args[0]
    assert compra.usuario_id == USUARIO_ID
    assert compra.impuesto_desglosado is True
    assert compra.requiere_revision is False
    linea = dobles.lineas.agregar.call_args.args[0]
    assert (linea.compra_id, linea.usuario_id, linea.categoria_id) == (101, USUARIO_ID, 30)
    dobles.sesion.commit.assert_called_once_with()


def test_la_bitacora_se_escribe_despues_de_confirmar(dobles: Dobles) -> None:
    """La bitácora explica lo que pasó, no lo decide: nunca antes del `commit`."""
    orden = Mock()
    orden.attach_mock(dobles.sesion.commit, "commit")
    orden.attach_mock(dobles.bitacora.registrar_evento, "bitacora")

    dobles.servicio.registrar(_comando())

    llamadas = [llamada[0] for llamada in orden.mock_calls]
    assert llamadas[0] == "commit"
    assert set(llamadas[1:]) == {"bitacora"}


def test_un_renglon_exento_no_lleva_impuesto(dobles: Dobles) -> None:
    registrada = dobles.servicio.registrar(
        _comando(lineas=(_linea(categoria_id=CATEGORIA_ID, exento_impuesto=True),))
    )

    assert registrada.impuesto == Decimal("0")
    assert registrada.total == Decimal("2000.00")


# ---- validaciones: cortan antes de escribir ----


def test_un_titular_desactivado_no_registra(dobles: Dobles) -> None:
    dobles.usuarios.obtener_por_id.return_value = Usuario(id=USUARIO_ID, activo=False)

    with pytest.raises(UsuarioInactivo):
        dobles.servicio.registrar(_comando())

    dobles.nada_se_escribio()


def test_un_titular_que_no_existe_no_registra(dobles: Dobles) -> None:
    dobles.usuarios.obtener_por_id.return_value = None

    with pytest.raises(RecursoNoEncontrado):
        dobles.servicio.registrar(_comando())

    dobles.nada_se_escribio()


def test_una_fecha_futura_se_rechaza(dobles: Dobles) -> None:
    with pytest.raises(FechaFutura):
        dobles.servicio.registrar(_comando(fecha=date.today() + timedelta(days=1)))

    dobles.nada_se_escribio()


def test_una_compra_sin_renglones_se_rechaza(dobles: Dobles) -> None:
    with pytest.raises(CompraSinRenglones):
        dobles.servicio.registrar(_comando(lineas=()))

    dobles.nada_se_escribio()


def test_el_descuento_de_un_renglon_no_supera_su_monto(dobles: Dobles) -> None:
    linea = _linea(categoria_id=CATEGORIA_ID, descuento=Decimal("2000.01"))

    with pytest.raises(DescuentoExcedido):
        dobles.servicio.registrar(_comando(lineas=(linea,)))

    dobles.nada_se_escribio()


def test_el_descuento_global_no_supera_el_subtotal(dobles: Dobles) -> None:
    with pytest.raises(DescuentoExcedido):
        dobles.servicio.registrar(_comando(descuento=Decimal("2000.01")))

    dobles.nada_se_escribio()


def test_una_moneda_extranjera_exige_su_tipo_de_cambio(dobles: Dobles) -> None:
    with pytest.raises(TipoDeCambioRequerido):
        dobles.servicio.registrar(_comando(moneda=Moneda.USD))

    dobles.nada_se_escribio()


def test_con_tipo_de_cambio_convierte_a_moneda_base(dobles: Dobles) -> None:
    registrada = dobles.servicio.registrar(
        _comando(moneda=Moneda.USD, tipo_cambio_aplicado=Decimal("550"))
    )

    assert registrada.total_moneda_base == Decimal("1243000.00")


# ---- el cuadre contra el recibo ----


def test_un_total_que_difiere_en_mas_de_un_colon_se_rechaza(dobles: Dobles) -> None:
    with pytest.raises(CuadreFueraDeTolerancia):
        dobles.servicio.registrar(_comando(total_declarado=Decimal("2261.01")))

    dobles.nada_se_escribio()


@pytest.mark.parametrize("declarado", ["2259.00", "2260.00", "2261.00"])
def test_una_diferencia_de_hasta_un_colon_cuadra(dobles: Dobles, declarado: str) -> None:
    registrada = dobles.servicio.registrar(_comando(total_declarado=Decimal(declarado)))

    assert registrada.total == Decimal("2260.00"), "el total es el calculado, no el declarado"


# ---- categorías y propiedad del recurso ----


def test_la_categoria_se_busca_por_id_y_por_titular(dobles: Dobles) -> None:
    """La verificación de propiedad: no existe una búsqueda de categoría sin el dueño."""
    dobles.servicio.registrar(_comando())

    dobles.categorias.obtener_de_usuario.assert_called_once_with(CATEGORIA_ID, USUARIO_ID)


def test_la_categoria_de_otro_titular_es_como_si_no_existiera(dobles: Dobles) -> None:
    dobles.categorias.obtener_de_usuario.return_value = None

    with pytest.raises(RecursoNoEncontrado):
        dobles.servicio.registrar(_comando())

    dobles.nada_se_escribio()


def test_una_categoria_padre_no_recibe_gasto(dobles: Dobles) -> None:
    dobles.categorias.obtener_de_usuario.return_value = _categoria(es_hoja=False)

    with pytest.raises(CategoriaNoEsHoja):
        dobles.servicio.registrar(_comando())

    dobles.nada_se_escribio()


def test_una_categoria_desactivada_no_recibe_gasto(dobles: Dobles) -> None:
    dobles.categorias.obtener_de_usuario.return_value = _categoria(activa=False)

    with pytest.raises(CategoriaInactiva):
        dobles.servicio.registrar(_comando())

    dobles.nada_se_escribio()


def test_un_renglon_que_nadie_sabe_clasificar_impide_registrar(dobles: Dobles) -> None:
    """Sin categoría elegida, sin regla que coincida y sin sugerencia del comercio."""
    with pytest.raises(RenglonSinCategoria):
        dobles.servicio.registrar(_comando(lineas=(_linea(),)))

    dobles.comercios.categoria_sugerida_para.assert_called_once_with(USUARIO_ID, COMERCIO_ID)
    dobles.nada_se_escribio()


def test_una_regla_que_acierta_clasifica_y_suma_su_contador(dobles: Dobles) -> None:
    regla = ReglaCategorizacion(
        id=9, usuario_id=USUARIO_ID, categoria_destino_id=CATEGORIA_ID, nombre="Walmart",
        patron="WALMART", prioridad=1, activa=True, veces_aplicada=4,
    )  # fmt: skip
    dobles.reglas.listar_activas_ordenadas.return_value = [regla]

    registrada = dobles.servicio.registrar(_comando(lineas=(_linea(), _linea())))

    assert all(linea.categorizada_automaticamente for linea in registrada.lineas)
    assert regla.veces_aplicada == 5, "una vez por compra, no una por renglón"
    dobles.reglas.listar_activas_ordenadas.assert_called_once_with(USUARIO_ID)
    dobles.comercios.categoria_sugerida_para.assert_not_called()


def test_sin_regla_decide_la_sugerencia_del_comercio(dobles: Dobles) -> None:
    dobles.comercios.categoria_sugerida_para.return_value = CATEGORIA_ID

    registrada = dobles.servicio.registrar(_comando(lineas=(_linea(),)))

    assert registrada.lineas[0].categoria_id == CATEGORIA_ID
    assert registrada.lineas[0].categorizada_automaticamente is True


def test_lo_que_el_titular_elige_gana_sobre_sus_reglas(dobles: Dobles) -> None:
    regla = ReglaCategorizacion(
        id=9, usuario_id=USUARIO_ID, categoria_destino_id=99, nombre="Walmart",
        patron="WALMART", prioridad=1, activa=True, veces_aplicada=0,
    )  # fmt: skip
    dobles.reglas.listar_activas_ordenadas.return_value = [regla]

    registrada = dobles.servicio.registrar(_comando())

    assert registrada.lineas[0].categoria_id == CATEGORIA_ID
    assert registrada.lineas[0].categorizada_automaticamente is False
    assert regla.veces_aplicada == 0
    dobles.reglas.listar_activas_ordenadas.assert_not_called()


# ---- método de pago ----


def test_el_metodo_de_pago_se_busca_por_id_y_por_titular(dobles: Dobles) -> None:
    dobles.metodos_pago.obtener_de_usuario.return_value = None

    with pytest.raises(RecursoNoEncontrado):
        dobles.servicio.registrar(_comando(metodo_pago_id=5))

    dobles.metodos_pago.obtener_de_usuario.assert_called_once_with(5, USUARIO_ID)
    dobles.nada_se_escribio()


def test_un_metodo_de_pago_desactivado_se_rechaza(dobles: Dobles) -> None:
    dobles.metodos_pago.obtener_de_usuario.return_value = MetodoPago(
        id=5, usuario_id=USUARIO_ID, alias="Visa", tipo=TipoMetodoPago.CREDITO, activo=False
    )

    with pytest.raises(MetodoPagoInactivo):
        dobles.servicio.registrar(_comando(metodo_pago_id=5))

    dobles.nada_se_escribio()


# ---- presupuesto ----


def _presupuesto(consumido: str, moneda: Moneda = Moneda.CRC) -> Presupuesto:
    return Presupuesto(
        id=40, usuario_id=USUARIO_ID, categoria_id=CATEGORIA_ID, anio=2026, mes=8,
        moneda=moneda, monto_limite=Decimal("10000.00"), monto_consumido=Decimal(consumido),
        umbral_alerta=80,
    )  # fmt: skip


def test_acumula_el_presupuesto_del_periodo_de_la_compra(dobles: Dobles) -> None:
    presupuesto = _presupuesto("1000.00")
    dobles.presupuestos.buscar.return_value = presupuesto

    registrada = dobles.servicio.registrar(_comando())

    dobles.presupuestos.buscar.assert_called_once_with(USUARIO_ID, CATEGORIA_ID, 2026, 8)
    assert presupuesto.monto_consumido == Decimal("3260.00"), "subtotal + impuesto del renglón"
    assert registrada.presupuestos_alertados == ()


def test_avisa_cuando_la_compra_cruza_el_umbral(dobles: Dobles) -> None:
    dobles.presupuestos.buscar.return_value = _presupuesto("6000.00")

    registrada = dobles.servicio.registrar(_comando())

    assert registrada.presupuestos_alertados == (40,), "6000 + 2260 = 82.6 % de 10000"


def test_no_vuelve_a_avisar_si_ya_estaba_sobre_el_umbral(dobles: Dobles) -> None:
    dobles.presupuestos.buscar.return_value = _presupuesto("8500.00")

    registrada = dobles.servicio.registrar(_comando())

    assert registrada.presupuestos_alertados == ()


def test_un_presupuesto_en_otra_moneda_no_se_toca(dobles: Dobles) -> None:
    presupuesto = _presupuesto("1000.00", moneda=Moneda.USD)
    dobles.presupuestos.buscar.return_value = presupuesto

    dobles.servicio.registrar(_comando())

    assert presupuesto.monto_consumido == Decimal("1000.00")
