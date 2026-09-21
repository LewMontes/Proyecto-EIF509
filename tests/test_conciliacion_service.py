"""El Proceso 2 del dominio -conciliación transaccional de un comprobante en una Compra
real- probado sin tocar red ni Mongo."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.parsers.comprobante_bac import ComprobanteParseado
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.categoria_service import CategoriaService, CrearCategoriaComando
from app.business.services.comercio_service import ComercioService
from app.business.services.conciliacion_service import ConciliacionService
from app.business.services.metodo_pago_service import CrearMetodoPagoComando, MetodoPagoService
from app.business.services.presupuesto_service import PresupuestoService
from app.business.services.tipo_cambio_service import TipoDeCambio
from app.data.models.comprobante import Comprobante
from app.data.models.cuenta_correo import CuentaCorreo
from app.data.models.enums import (
    CampoRegla,
    EstadoCuentaCorreo,
    Moneda,
    ProveedorCorreo,
    TipoMetodoPago,
)
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.models.usuario import Usuario
from app.data.repositories.bitacora_repository import BitacoraRepository
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.comprobante_repository import ComprobanteRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.tipo_cambio_repository import TipoCambioRepository
from app.data.repositories.usuario_repository import UsuarioRepository


class _TipoCambioFalso:
    """Doble de TipoCambioService: siempre la misma tasa, sin tocar la red."""

    def __init__(self, venta: Decimal = Decimal("550.00")) -> None:
        self._venta = venta

    def obtener(self, fecha: date | None = None) -> TipoDeCambio:
        return TipoDeCambio(
            fecha=fecha or date(2026, 8, 30), compra=self._venta - 5, venta=self._venta
        )


def _armar(sesion: Session, tipo_cambio=None) -> ConciliacionService:
    return ConciliacionService(
        CompraRepository(sesion),
        LineaCompraRepository(sesion),
        MetodoPagoRepository(sesion),
        ReglaCategorizacionRepository(sesion),
        PresupuestoRepository(sesion),
        CategoriaRepository(sesion),
        ComercioCategoriaRepository(sesion),
        TipoCambioRepository(sesion),
        ComprobanteRepository(sesion),
        ComercioService(
            ComercioRepository(sesion),
            ComercioCategoriaRepository(sesion),
            CategoriaRepository(sesion),
        ),
        tipo_cambio,
        BitacoraComprasService(BitacoraRepository(None)),
    )


@pytest.fixture
def servicio(sesion: Session) -> ConciliacionService:
    return _armar(sesion)


@pytest.fixture
def servicio_con_tasa(sesion: Session) -> ConciliacionService:
    return _armar(sesion, _TipoCambioFalso())


@pytest.fixture
def metodos_pago(sesion: Session) -> MetodoPagoService:
    return MetodoPagoService(MetodoPagoRepository(sesion), UsuarioRepository(sesion))


@pytest.fixture
def presupuestos(sesion: Session) -> PresupuestoService:
    return PresupuestoService(
        PresupuestoRepository(sesion), CategoriaRepository(sesion), UsuarioRepository(sesion)
    )


@pytest.fixture
def categorias(sesion: Session) -> CategoriaService:
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


@pytest.fixture
def cuenta_correo(sesion: Session, usuario: Usuario) -> CuentaCorreo:
    cuenta = CuentaCorreo(
        usuario_id=usuario.id,
        proveedor=ProveedorCorreo.OUTLOOK,
        direccion="titular@hotmail.com",
        token_acceso_cifrado="cifrado",
        token_refresco_cifrado="cifrado",
        expira_en=datetime.now(UTC),
        estado=EstadoCuentaCorreo.ACTIVA,
    )
    sesion.add(cuenta)
    sesion.commit()
    return cuenta


def _parseado(**overrides) -> ComprobanteParseado:
    base = dict(
        banco="BAC Credomatic",
        comercio="WALMART SAN SEBASTIAN",
        ciudad="SAN JOSE",
        pais="Costa Rica",
        fecha=datetime(2026, 8, 30, 13, 27),
        marca_tarjeta="AMEX",
        ultimos_cuatro="4321",
        autorizacion="100200",
        referencia="99887766",
        tipo_transaccion="COMPRA",
        moneda="CRC",
        monto=Decimal("7870.00"),
        confianza=1.0,
    )
    base.update(overrides)
    return ComprobanteParseado(**base)


def _comprobante(
    sesion: Session, cuenta_correo: CuentaCorreo, mensaje_id: str = "1"
) -> Comprobante:
    fila = Comprobante(
        cuenta_correo_id=cuenta_correo.id,
        mensaje_id=mensaje_id,
        banco="BAC Credomatic",
        confianza=1.0,
    )
    sesion.add(fila)
    sesion.commit()
    return fila


# ---- casos que ni siquiera intentan conciliar ----


def test_una_notificacion_no_confiable_no_concilia(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado(confianza=0.5))

    assert resultado is None
    assert comprobante.compra_id is None


def test_una_anulacion_no_concilia(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado(tipo_transaccion="ANULACION"))

    assert resultado is None


def test_sin_comercio_no_concilia(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado(comercio=None))

    assert resultado is None


# ---- conciliación real ----


def test_concilia_una_compra_completa(
    servicio: ConciliacionService,
    metodos_pago: MetodoPagoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    metodos_pago.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Amex", tipo=TipoMetodoPago.CREDITO, ultimos_cuatro="4321"
        )
    )
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    assert resultado is not None
    assert resultado.requiere_revision is False
    assert comprobante.compra_id == resultado.compra_id

    compra = servicio.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    assert compra.total == Decimal("7870.00")
    assert compra.moneda == Moneda.CRC
    assert compra.metodo_pago_id is not None
    assert compra.requiere_revision is False

    lineas = servicio.lineas.listar_de_compra(compra.id)
    assert len(lineas) == 1
    assert lineas[0].subtotal == Decimal("7870.00")


def test_sin_metodo_de_pago_registrado_queda_para_revision(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    assert resultado.requiere_revision is True
    compra = servicio.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    assert compra.metodo_pago_id is None, "nunca se inventa un metodo de pago"


def test_nunca_inventa_un_metodo_de_pago_aunque_haya_otras_tarjetas(
    servicio: ConciliacionService,
    metodos_pago: MetodoPagoService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    metodos_pago.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Otra", tipo=TipoMetodoPago.DEBITO, ultimos_cuatro="9999"
        )
    )
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    compra = servicio.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    assert compra.metodo_pago_id is None


def test_una_compra_sin_categoria_disponible_queda_sin_clasificar(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    assert resultado.requiere_revision is True
    compra = servicio.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    lineas = servicio.lineas.listar_de_compra(compra.id)
    assert lineas[0].categoria_id is None
    assert lineas[0].categorizada_automaticamente is False


def test_una_regla_activa_categoriza_automatico(
    servicio: ConciliacionService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E")
    )
    regla = ReglaCategorizacion(
        usuario_id=usuario.id,
        categoria_destino_id=categoria.id,
        nombre="Walmart es supermercado",
        campo=CampoRegla.COMERCIO_NORMALIZADO,
        patron="WALMART",
        prioridad=1,
    )
    sesion.add(regla)
    sesion.commit()
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    compra = servicio.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    lineas = servicio.lineas.listar_de_compra(compra.id)
    assert lineas[0].categoria_id == categoria.id
    assert lineas[0].categorizada_automaticamente is True
    assert servicio.reglas.obtener_de_usuario(regla.id, usuario.id).veces_aplicada == 1


def test_una_regla_gana_sobre_la_sugerencia_del_comercio(
    servicio: ConciliacionService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    """La regla se evalúa primero -ver `ConciliacionService._categorizar`."""
    sugerida = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Otros", color_hex="#6B7280")
    )
    por_regla = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, sugerida.id)
    sesion.add(
        ReglaCategorizacion(
            usuario_id=usuario.id,
            categoria_destino_id=por_regla.id,
            nombre="Walmart",
            campo=CampoRegla.COMERCIO_NORMALIZADO,
            patron="WALMART",
            prioridad=1,
        )
    )
    sesion.commit()
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    lineas = servicio.lineas.listar_de_compra(resultado.compra_id)
    assert lineas[0].categoria_id == por_regla.id


def test_convierte_a_la_tasa_de_la_compra_en_dolares(
    servicio_con_tasa: ConciliacionService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio_con_tasa.conciliar(
        usuario.id, comprobante, _parseado(moneda="USD", monto=Decimal("10.00"))
    )

    compra = servicio_con_tasa.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    assert compra.moneda == Moneda.USD
    assert compra.total == Decimal("10.00")
    assert compra.tipo_cambio_aplicado == Decimal("550.000000")
    assert compra.total_moneda_base == Decimal("5500.00")


def test_sin_servicio_de_tipo_cambio_no_convierte(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(
        usuario.id, comprobante, _parseado(moneda="USD", monto=Decimal("10.00"))
    )

    compra = servicio.compras.obtener_de_usuario(resultado.compra_id, usuario.id)
    assert compra.tipo_cambio_aplicado == Decimal("1")
    assert compra.total_moneda_base == Decimal("10.00")


# ---- presupuesto ----


def test_acumula_el_presupuesto_de_la_categoria_y_periodo(
    servicio: ConciliacionService,
    presupuestos: PresupuestoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    presupuesto = presupuestos.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("10000")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    assert resultado.requiere_revision is True, "sigue sin metodo de pago"
    assert resultado.presupuesto_alertado is False
    actualizado = presupuestos.presupuestos.obtener_de_usuario(presupuesto.id, usuario.id)
    assert actualizado.monto_consumido == Decimal("7870.00")


def test_marca_alerta_de_presupuesto_al_cruzar_el_umbral(
    servicio: ConciliacionService,
    presupuestos: PresupuestoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    presupuestos.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("8000"), umbral_alerta=80
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    assert resultado.presupuesto_alertado is True


def test_una_categoria_sin_presupuesto_no_acumula_nada(
    servicio: ConciliacionService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)
    comprobante = _comprobante(sesion, cuenta_correo)

    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    assert resultado.presupuesto_alertado is False


# ---- corrección retroactiva ----


def test_recategorizar_comercio_corrige_compras_ya_conciliadas(
    servicio: ConciliacionService,
    presupuestos: PresupuestoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    presupuesto = presupuestos.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("10000")
    )
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())
    assert resultado.requiere_revision is True, "sin categoria todavia"

    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    corregidas = servicio.recategorizar_compras_de_comercio(usuario.id, comercio.id, categoria.id)

    assert corregidas == 1
    lineas = servicio.lineas.listar_de_compra(resultado.compra_id)
    assert lineas[0].categoria_id == categoria.id
    actualizado = presupuestos.presupuestos.obtener_de_usuario(presupuesto.id, usuario.id)
    assert actualizado.monto_consumido == Decimal("7870.00")


def test_recategorizar_no_toca_una_compra_que_ya_tenia_categoria(
    servicio: ConciliacionService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria_original = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    otra_categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Otros", color_hex="#6B7280")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria_original.id)
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    corregidas = servicio.recategorizar_compras_de_comercio(
        usuario.id, comercio.id, otra_categoria.id
    )

    assert corregidas == 0
    lineas = servicio.lineas.listar_de_compra(resultado.compra_id)
    assert lineas[0].categoria_id == categoria_original.id


# ---- resolver_revision: corrección manual de una compra puntual ----


def test_resolver_revision_sin_ningun_campo_falla(
    servicio: ConciliacionService, usuario: Usuario, cuenta_correo: CuentaCorreo, sesion: Session
) -> None:
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    with pytest.raises(DatosInvalidos):
        servicio.resolver_revision(usuario.id, resultado.compra_id, None, None)


def test_resolver_revision_de_compra_que_no_existe_falla(
    servicio: ConciliacionService, usuario: Usuario
) -> None:
    with pytest.raises(RecursoNoEncontrado):
        servicio.resolver_revision(usuario.id, 999999, None, 1)


def test_resolver_revision_asigna_metodo_de_pago_y_quita_la_marca(
    servicio: ConciliacionService,
    metodos_pago: MetodoPagoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())
    assert resultado.requiere_revision is True, "sin metodo de pago todavia"

    metodo = metodos_pago.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Amex", tipo=TipoMetodoPago.CREDITO, ultimos_cuatro="4321"
        )
    )

    corregida = servicio.resolver_revision(usuario.id, resultado.compra_id, metodo.id, None)

    assert corregida.metodo_pago_id == metodo.id
    assert corregida.requiere_revision is False


def test_resolver_revision_asigna_categoria_y_acumula_presupuesto(
    servicio: ConciliacionService,
    metodos_pago: MetodoPagoService,
    presupuestos: PresupuestoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    metodos_pago.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Amex", tipo=TipoMetodoPago.CREDITO, ultimos_cuatro="4321"
        )
    )
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    presupuesto = presupuestos.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("10000")
    )
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())
    assert resultado.requiere_revision is True, "sin categoria todavia"

    corregida = servicio.resolver_revision(usuario.id, resultado.compra_id, None, categoria.id)

    assert corregida.requiere_revision is False
    lineas = servicio.lineas.listar_de_compra(corregida.id)
    assert lineas[0].categoria_id == categoria.id
    actualizado = presupuestos.presupuestos.obtener_de_usuario(presupuesto.id, usuario.id)
    assert actualizado.monto_consumido == Decimal("7870.00")


def test_resolver_revision_no_toca_presupuesto_si_ya_tenia_categoria(
    servicio: ConciliacionService,
    metodos_pago: MetodoPagoService,
    presupuestos: PresupuestoService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    """Corregir una categoría que ya estaba asignada no mueve plata entre presupuestos
    -ver la nota de `ConciliacionService.resolver_revision`."""
    categoria_original = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    categoria_nueva = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Otros", color_hex="#6B7280")
    )
    presupuesto_original = presupuestos.crear_o_actualizar(
        usuario.id, categoria_original.id, 2026, 8, Moneda.CRC, Decimal("10000")
    )
    presupuesto_nuevo = presupuestos.crear_o_actualizar(
        usuario.id, categoria_nueva.id, 2026, 8, Moneda.CRC, Decimal("10000")
    )
    comercio = servicio.comercios_servicio.resolver_o_crear("WALMART SAN SEBASTIAN")
    servicio.comercios_servicio.asignar_categoria(usuario.id, comercio.id, categoria_original.id)
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())
    consumido_antes = presupuestos.presupuestos.obtener_de_usuario(
        presupuesto_original.id, usuario.id
    ).monto_consumido

    servicio.resolver_revision(usuario.id, resultado.compra_id, None, categoria_nueva.id)

    lineas = servicio.lineas.listar_de_compra(resultado.compra_id)
    assert lineas[0].categoria_id == categoria_nueva.id
    original_despues = presupuestos.presupuestos.obtener_de_usuario(
        presupuesto_original.id, usuario.id
    )
    nuevo_despues = presupuestos.presupuestos.obtener_de_usuario(presupuesto_nuevo.id, usuario.id)
    assert original_despues.monto_consumido == consumido_antes
    assert nuevo_despues.monto_consumido == Decimal("0")


def test_resolver_revision_rechaza_metodo_de_pago_desactivado(
    servicio: ConciliacionService,
    metodos_pago: MetodoPagoService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    metodo = metodos_pago.crear(
        CrearMetodoPagoComando(usuario_id=usuario.id, alias="Amex", tipo=TipoMetodoPago.CREDITO)
    )
    metodos_pago.desactivar(usuario.id, metodo.id)
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.resolver_revision(usuario.id, resultado.compra_id, metodo.id, None)


def test_resolver_revision_rechaza_categoria_que_no_es_hoja(
    servicio: ConciliacionService,
    categorias: CategoriaService,
    usuario: Usuario,
    cuenta_correo: CuentaCorreo,
    sesion: Session,
) -> None:
    grupo = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#16A34A")
    )
    categorias.crear(
        CrearCategoriaComando(
            usuario_id=usuario.id,
            nombre="Supermercado",
            color_hex="#22C55E",
            categoria_padre_id=grupo.id,
        )
    )
    comprobante = _comprobante(sesion, cuenta_correo)
    resultado = servicio.conciliar(usuario.id, comprobante, _parseado())

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.resolver_revision(usuario.id, resultado.compra_id, None, grupo.id)
