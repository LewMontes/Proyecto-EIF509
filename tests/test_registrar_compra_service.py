"""El Proceso 1 del dominio -registro manual de una compra con desglose- regla por regla.

Camino feliz y un caso por cada regla y cada validación que el servicio hace
valer, más los cálculos del desglose (subtotal de renglón, impuesto, descuento
global, cuadre contra el recibo y conversión de moneda).

Corren sobre SQLite en memoria: la sesión es real -lo que se prueba incluye
que la transacción quede coherente, y con un repositorio simulado eso no se
vería- pero nada sale a la red ni a Mongo.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.comercio_service import ComercioService
from app.business.services.registrar_compra_service import (
    LineaDeCompraComando,
    RegistrarCompraComando,
    RegistrarCompraService,
)
from app.data.models.categoria import Categoria
from app.data.models.enums import CampoRegla, EstadoCompra, Moneda, OrigenCompra, TipoMetodoPago
from app.data.models.metodo_pago import MetodoPago
from app.data.models.presupuesto import Presupuesto
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.models.usuario import Usuario
from app.data.repositories.bitacora_repository import BitacoraRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.usuario_repository import UsuarioRepository

FECHA = date(2026, 8, 30)


@pytest.fixture
def comercios(sesion: Session) -> ComercioService:
    return ComercioService(
        ComercioRepository(sesion),
        ComercioCategoriaRepository(sesion),
        CategoriaRepository(sesion),
    )


@pytest.fixture
def servicio(sesion: Session, comercios: ComercioService) -> RegistrarCompraService:
    return RegistrarCompraService(
        CompraRepository(sesion),
        LineaCompraRepository(sesion),
        CategoriaRepository(sesion),
        MetodoPagoRepository(sesion),
        PresupuestoRepository(sesion),
        ReglaCategorizacionRepository(sesion),
        UsuarioRepository(sesion),
        comercios,
        BitacoraComprasService(BitacoraRepository(None)),
    )


@pytest.fixture
def comercio(comercios: ComercioService):
    return comercios.resolver_o_crear("Walmart San Sebastián")


def _categoria(sesion: Session, usuario: Usuario, nombre: str = "Supermercado", **kwargs):
    categoria = Categoria(
        usuario_id=usuario.id,
        nombre=nombre,
        color_hex="#2563EB",
        es_hoja=kwargs.pop("es_hoja", True),
        activa=kwargs.pop("activa", True),
        **kwargs,
    )
    sesion.add(categoria)
    sesion.commit()
    return categoria


def _linea(**overrides) -> LineaDeCompraComando:
    base = dict(
        descripcion="Leche 1L",
        cantidad=Decimal("2"),
        precio_unitario=Decimal("1000.00"),
    )
    base.update(overrides)
    return LineaDeCompraComando(**base)


def _comando(usuario: Usuario, comercio, **overrides) -> RegistrarCompraComando:
    base = dict(
        usuario_id=usuario.id,
        comercio_id=comercio.id,
        fecha=FECHA,
        lineas=(_linea(),),
    )
    base.update(overrides)
    return RegistrarCompraComando(**base)


# ---- camino feliz y cálculos ----


def test_registra_una_compra_y_calcula_el_impuesto(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)

    registrada = servicio.registrar(
        _comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),))
    )

    # 2 × 1000 = 2000 de subtotal; 13% de IVA = 260; total 2260.
    assert registrada.subtotal == Decimal("2000.00")
    assert registrada.impuesto == Decimal("260.00")
    assert registrada.total == Decimal("2260.00")
    assert registrada.total_moneda_base == Decimal("2260.00")
    assert registrada.estado == EstadoCompra.REGISTRADA
    assert registrada.lineas[0].categoria_nombre == "Supermercado"


def test_la_compra_queda_como_manual_y_con_el_impuesto_desglosado(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Lo que la distingue de una compra ingerida por correo.

    La ingesta guarda un total opaco con el IVA ya adentro
    (`impuesto_desglosado = False`); acá el impuesto se calculó renglón por
    renglón, así que la compra puede decir que sí lo tiene desglosado -y la
    base lo distingue con un CHECK.
    """
    categoria = _categoria(sesion, usuario)
    registrada = servicio.registrar(
        _comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),))
    )

    compra = CompraRepository(sesion).obtener_de_usuario(registrada.compra_id, usuario.id)
    assert compra.origen == OrigenCompra.MANUAL
    assert compra.impuesto_desglosado is True
    assert compra.requiere_revision is False


def test_suma_varios_renglones_y_resta_el_descuento_global_al_final(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """El descuento global no se prorratea: se resta después de sumar.

    Es lo que permite que el titular vea de dónde salió la rebaja en vez de
    encontrarla repartida en pedacitos entre los renglones.
    """
    categoria = _categoria(sesion, usuario)
    registrada = servicio.registrar(
        _comando(
            usuario,
            comercio,
            lineas=(
                _linea(categoria_id=categoria.id),
                _linea(
                    descripcion="Pan",
                    cantidad=Decimal("1"),
                    precio_unitario=Decimal("500.00"),
                    categoria_id=categoria.id,
                ),
            ),
            descuento=Decimal("300.00"),
        )
    )

    # 2000 + 500 = 2500 de subtotal; IVA 260 + 65 = 325; total 2500 - 300 + 325.
    assert registrada.subtotal == Decimal("2500.00")
    assert registrada.impuesto == Decimal("325.00")
    assert registrada.total == Decimal("2525.00")
    assert len(registrada.lineas) == 2


def test_un_renglon_exento_no_paga_impuesto(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Exento es una propiedad del producto (canasta básica, medicamentos),
    por eso se captura por renglón y no por compra."""
    categoria = _categoria(sesion, usuario)
    registrada = servicio.registrar(
        _comando(
            usuario,
            comercio,
            lineas=(
                _linea(categoria_id=categoria.id, exento_impuesto=True),
                _linea(
                    descripcion="Jabón",
                    cantidad=Decimal("1"),
                    precio_unitario=Decimal("1000.00"),
                    categoria_id=categoria.id,
                ),
            ),
        )
    )

    assert registrada.lineas[0].impuesto == Decimal("0")
    assert registrada.lineas[1].impuesto == Decimal("130.00")
    assert registrada.impuesto == Decimal("130.00")


def test_el_descuento_del_renglon_se_resta_antes_del_impuesto(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    registrada = servicio.registrar(
        _comando(
            usuario,
            comercio,
            lineas=(_linea(categoria_id=categoria.id, descuento=Decimal("200.00")),),
        )
    )

    # (2 × 1000) − 200 = 1800; 13% de 1800 = 234.
    assert registrada.lineas[0].subtotal == Decimal("1800.00")
    assert registrada.lineas[0].impuesto == Decimal("234.00")


# ---- validaciones de forma del negocio ----


def test_rechaza_una_fecha_futura(servicio, sesion: Session, usuario: Usuario, comercio) -> None:
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="futura"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                fecha=date.today() + timedelta(days=1),
                lineas=(_linea(categoria_id=categoria.id),),
            )
        )


def test_rechaza_una_compra_sin_renglones(servicio, usuario: Usuario, comercio) -> None:
    with pytest.raises(DatosInvalidos, match="al menos un renglón"):
        servicio.registrar(_comando(usuario, comercio, lineas=()))


def test_rechaza_una_cantidad_que_no_es_positiva(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="mayor que cero"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(cantidad=Decimal("0"), categoria_id=categoria.id),),
            )
        )


def test_rechaza_un_precio_unitario_negativo(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="no puede ser negativo"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(precio_unitario=Decimal("-1"), categoria_id=categoria.id),),
            )
        )


def test_rechaza_un_descuento_de_renglon_mayor_que_el_renglon(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """«Ningún descuento puede superar el monto sobre el que se aplica»."""
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="supera el monto"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(descuento=Decimal("5000.00"), categoria_id=categoria.id),),
            )
        )


def test_rechaza_un_descuento_global_mayor_que_el_subtotal(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="no puede superar el subtotal"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(categoria_id=categoria.id),),
                descuento=Decimal("9999.00"),
            )
        )


# ---- cuadre contra el recibo ----


def test_acepta_el_total_del_recibo_dentro_de_un_colon(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """La tolerancia existe porque el comercio redondea distinto, no para
    tapar un renglón mal digitado."""
    categoria = _categoria(sesion, usuario)
    registrada = servicio.registrar(
        _comando(
            usuario,
            comercio,
            lineas=(_linea(categoria_id=categoria.id),),
            total_declarado=Decimal("2259.00"),
        )
    )
    assert registrada.total == Decimal("2260.00"), "manda el calculado, no el declarado"


def test_rechaza_el_total_del_recibo_si_difiere_mas_de_un_colon(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    with pytest.raises(ReglaDeNegocioViolada, match="no cuadra"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(categoria_id=categoria.id),),
                total_declarado=Decimal("2000.00"),
            )
        )


# ---- pertenencia y estado de lo referenciado ----


def test_rechaza_una_categoria_de_otro_titular(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """La validación que impide tocar datos de otra cuenta pasando un id ajeno."""
    otro = Usuario(nombre_completo="Otra", correo="otra@gastonomo.cr", contrasena_hash="x")
    sesion.add(otro)
    sesion.commit()
    ajena = _categoria(sesion, otro, nombre="Ajena")

    with pytest.raises(RecursoNoEncontrado, match="no existe en esta cuenta"):
        servicio.registrar(_comando(usuario, comercio, lineas=(_linea(categoria_id=ajena.id),)))


def test_rechaza_una_categoria_padre(servicio, sesion: Session, usuario: Usuario, comercio) -> None:
    """Las padre totalizan; solo las hojas reciben gasto directo."""
    padre = _categoria(sesion, usuario, nombre="Alimentación", es_hoja=False)
    with pytest.raises(ReglaDeNegocioViolada, match="categoría padre"):
        servicio.registrar(_comando(usuario, comercio, lineas=(_linea(categoria_id=padre.id),)))


def test_rechaza_una_categoria_desactivada(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    inactiva = _categoria(sesion, usuario, nombre="Vieja", activa=False)
    with pytest.raises(ReglaDeNegocioViolada, match="desactivada"):
        servicio.registrar(_comando(usuario, comercio, lineas=(_linea(categoria_id=inactiva.id),)))


def test_rechaza_un_metodo_de_pago_desactivado(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    metodo = MetodoPago(
        usuario_id=usuario.id,
        alias="Visa vieja",
        tipo=TipoMetodoPago.CREDITO,
        moneda=Moneda.CRC,
        activo=False,
    )
    sesion.add(metodo)
    sesion.commit()

    with pytest.raises(ReglaDeNegocioViolada, match="desactivado"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(categoria_id=categoria.id),),
                metodo_pago_id=metodo.id,
            )
        )


def test_rechaza_un_comercio_que_no_existe(servicio, sesion: Session, usuario: Usuario) -> None:
    categoria = _categoria(sesion, usuario)
    comando = RegistrarCompraComando(
        usuario_id=usuario.id,
        comercio_id=9999,
        fecha=FECHA,
        lineas=(_linea(categoria_id=categoria.id),),
    )
    with pytest.raises(RecursoNoEncontrado, match="comercio"):
        servicio.registrar(comando)


# ---- la cadena de categorización ----


def test_una_regla_activa_categoriza_el_renglon_sin_categoria(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Misma cadena que la ingesta por correo: primero las reglas del titular."""
    categoria = _categoria(sesion, usuario)
    sesion.add(
        ReglaCategorizacion(
            usuario_id=usuario.id,
            categoria_destino_id=categoria.id,
            nombre="Supermercados",
            campo=CampoRegla.COMERCIO_NORMALIZADO,
            patron="WALMART",
            prioridad=1,
        )
    )
    sesion.commit()

    registrada = servicio.registrar(_comando(usuario, comercio))

    assert registrada.lineas[0].categoria_id == categoria.id
    assert registrada.lineas[0].categorizada_automaticamente is True


def test_si_ninguna_regla_coincide_cae_a_la_sugerencia_del_comercio(
    servicio, comercios: ComercioService, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    comercios.asignar_categoria(usuario.id, comercio.id, categoria.id)

    registrada = servicio.registrar(_comando(usuario, comercio))

    assert registrada.lineas[0].categoria_id == categoria.id
    assert registrada.lineas[0].categorizada_automaticamente is True


def test_la_categoria_que_eligio_el_titular_gana_sobre_la_regla(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Corregir es lo que hace aprender al sistema: la decisión de la persona
    no puede quedar pisada por una regla que ella misma creó antes."""
    de_la_regla = _categoria(sesion, usuario, nombre="Supermercado")
    elegida = _categoria(sesion, usuario, nombre="Mascotas")
    sesion.add(
        ReglaCategorizacion(
            usuario_id=usuario.id,
            categoria_destino_id=de_la_regla.id,
            nombre="Supermercados",
            patron="WALMART",
            prioridad=1,
        )
    )
    sesion.commit()

    registrada = servicio.registrar(
        _comando(usuario, comercio, lineas=(_linea(categoria_id=elegida.id),))
    )

    assert registrada.lineas[0].categoria_id == elegida.id
    assert registrada.lineas[0].categorizada_automaticamente is False


def test_sin_categoria_ni_sugerencia_la_compra_no_se_registra(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """«Una compra REGISTRADA no admite renglones sin categoría»: si se
    permitiera, los reportes mostrarían menos gasto del real."""
    with pytest.raises(ReglaDeNegocioViolada, match="no admite renglones sin clasificar"):
        servicio.registrar(_comando(usuario, comercio))

    assert CompraRepository(sesion).listar_de_usuario(usuario.id) == []


def test_la_regla_que_acerto_sube_su_contador_una_sola_vez_por_compra(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Dos renglones categorizados por la misma regla son una sola aplicación
    de esa regla: contarla dos veces inflaría la estadística de qué tan útil es."""
    categoria = _categoria(sesion, usuario)
    regla = ReglaCategorizacion(
        usuario_id=usuario.id,
        categoria_destino_id=categoria.id,
        nombre="Supermercados",
        patron="WALMART",
        prioridad=1,
    )
    sesion.add(regla)
    sesion.commit()

    servicio.registrar(_comando(usuario, comercio, lineas=(_linea(), _linea(descripcion="Pan"))))

    sesion.refresh(regla)
    assert regla.veces_aplicada == 1


# ---- impacto en los presupuestos ----


def _presupuesto(sesion: Session, usuario: Usuario, categoria, **kwargs) -> Presupuesto:
    presupuesto = Presupuesto(
        usuario_id=usuario.id,
        categoria_id=categoria.id,
        anio=FECHA.year,
        mes=FECHA.month,
        moneda=kwargs.pop("moneda", Moneda.CRC),
        monto_limite=kwargs.pop("monto_limite", Decimal("100000.00")),
        monto_consumido=kwargs.pop("monto_consumido", Decimal("0.00")),
        umbral_alerta=kwargs.pop("umbral_alerta", 80),
    )
    sesion.add(presupuesto)
    sesion.commit()
    return presupuesto


def test_acumula_el_presupuesto_de_la_categoria_del_renglon(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Cada categoría recibe lo que costaron sus renglones, no el total de la
    compra: si cada presupuesto se llevara el total, una compra desglosada en
    tres categorías contaría el triple."""
    categoria = _categoria(sesion, usuario)
    presupuesto = _presupuesto(sesion, usuario, categoria)

    servicio.registrar(_comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),)))

    sesion.refresh(presupuesto)
    assert presupuesto.monto_consumido == Decimal("2260.00"), "subtotal + impuesto del renglón"


def test_no_acumula_un_presupuesto_en_otra_moneda(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Sumar colones sobre un límite en dólares daría un número inventado."""
    categoria = _categoria(sesion, usuario)
    presupuesto = _presupuesto(sesion, usuario, categoria, moneda=Moneda.USD)

    servicio.registrar(_comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),)))

    sesion.refresh(presupuesto)
    assert presupuesto.monto_consumido == Decimal("0.00")


def test_marca_la_alerta_al_cruzar_el_umbral(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    presupuesto = _presupuesto(
        sesion, usuario, categoria, monto_limite=Decimal("3000.00"), umbral_alerta=80
    )

    registrada = servicio.registrar(
        _comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),))
    )

    # 2260 de 3000 es 75.33%: todavía por debajo del umbral del 80%.
    assert registrada.presupuestos_alertados == ()

    registrada = servicio.registrar(
        _comando(
            usuario,
            comercio,
            lineas=(
                _linea(
                    descripcion="Pan",
                    cantidad=Decimal("1"),
                    precio_unitario=Decimal("200.00"),
                    categoria_id=categoria.id,
                ),
            ),
        )
    )
    # +226 (200 + IVA) deja el consumo en 2486 de 3000: 82.87%, cruzó el 80%.
    assert registrada.presupuestos_alertados == (presupuesto.id,)


def test_la_alerta_no_se_repite_en_la_compra_siguiente(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """Avisar en cada compra posterior al umbral sería ruido: el titular ya
    sabe que lo cruzó."""
    categoria = _categoria(sesion, usuario)
    _presupuesto(sesion, usuario, categoria, monto_limite=Decimal("2500.00"))

    primera = servicio.registrar(
        _comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),))
    )
    segunda = servicio.registrar(
        _comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),))
    )

    assert primera.presupuestos_alertados != ()
    assert segunda.presupuestos_alertados == ()


# ---- moneda ----


def test_una_compra_en_colones_no_lleva_conversion(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="no lleva conversión"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(categoria_id=categoria.id),),
                tipo_cambio_aplicado=Decimal("550"),
            )
        )


def test_una_compra_en_dolares_sin_tasa_no_se_registra(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    """No se usa la tasa de hoy: el titular puede estar capturando una compra
    de hace meses, y esa no es la que pagó."""
    categoria = _categoria(sesion, usuario)
    with pytest.raises(DatosInvalidos, match="tipo de cambio de su fecha"):
        servicio.registrar(
            _comando(
                usuario,
                comercio,
                lineas=(_linea(categoria_id=categoria.id),),
                moneda=Moneda.USD,
            )
        )


def test_una_compra_en_dolares_con_tasa_convierte_el_total(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    registrada = servicio.registrar(
        _comando(
            usuario,
            comercio,
            lineas=(
                _linea(
                    cantidad=Decimal("1"),
                    precio_unitario=Decimal("10.00"),
                    categoria_id=categoria.id,
                ),
            ),
            moneda=Moneda.USD,
            tipo_cambio_aplicado=Decimal("536.784512"),
        )
    )

    # 10 + 13% = 11.30; 11.30 × 536.784512 = 6065.6649856 -> 6065.66
    assert registrada.total == Decimal("11.30")
    assert registrada.total_moneda_base == Decimal("6065.66")


# ---- titular ----


def test_rechaza_un_titular_desactivado(
    servicio, sesion: Session, usuario: Usuario, comercio
) -> None:
    categoria = _categoria(sesion, usuario)
    usuario.activo = False
    sesion.commit()

    with pytest.raises(ReglaDeNegocioViolada, match="desactivado"):
        servicio.registrar(_comando(usuario, comercio, lineas=(_linea(categoria_id=categoria.id),)))
