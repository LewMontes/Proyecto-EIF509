"""Reglas de negocio del catálogo de comercios, sin tocar red."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.parsers.comprobante_bac import ComprobanteParseado
from app.business.services.categoria_service import CategoriaService, CrearCategoriaComando
from app.business.services.comercio_service import ComercioService, normalizar_nombre_comercio
from app.data.models.enums import Moneda
from app.data.models.usuario import Usuario
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository
from app.data.repositories.usuario_repository import UsuarioRepository


@pytest.fixture
def servicio(sesion: Session) -> ComercioService:
    return ComercioService(
        ComercioRepository(sesion), ComercioCategoriaRepository(sesion), CategoriaRepository(sesion)
    )


@pytest.fixture
def categorias(sesion: Session) -> CategoriaService:
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


def _comprobante(
    comercio: str | None = "WALMART SAN SEBASTIAN",
    monto: Decimal | None = Decimal("100.00"),
    moneda: str | None = "CRC",
    tipo_transaccion: str | None = "COMPRA",
    confianza: float = 1.0,
) -> ComprobanteParseado:
    return ComprobanteParseado(
        banco="BAC Credomatic",
        comercio=comercio,
        ciudad=None,
        pais=None,
        fecha=datetime(2026, 8, 15),
        marca_tarjeta="VISA",
        ultimos_cuatro="1234",
        autorizacion="1",
        referencia="1",
        tipo_transaccion=tipo_transaccion,
        moneda=moneda,
        monto=monto,
        confianza=confianza,
    )


def test_normaliza_mayusculas_acentos_y_espacios() -> None:
    assert normalizar_nombre_comercio("  Walmart   San Sebastián  ") == "WALMART SAN SEBASTIAN"
    assert normalizar_nombre_comercio("WALMART SAN SEBASTIAN") == "WALMART SAN SEBASTIAN"


def test_resolver_o_crear_no_duplica_variantes_del_mismo_nombre(servicio: ComercioService) -> None:
    primero = servicio.resolver_o_crear("Walmart San Sebastián")
    segundo = servicio.resolver_o_crear("WALMART SAN SEBASTIAN")

    assert primero.id == segundo.id


def test_resolver_o_crear_rechaza_nombre_vacio(servicio: ComercioService) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.resolver_o_crear("   ")


def test_asignar_categoria_crea_la_sugerencia(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario
) -> None:
    comercio = servicio.resolver_o_crear("Walmart San Sebastián")
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)

    assert servicio.categoria_sugerida_para(usuario.id, comercio.id) == categoria.id


def test_asignar_categoria_dos_veces_corrige_en_vez_de_duplicar(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario
) -> None:
    comercio = servicio.resolver_o_crear("Walmart San Sebastián")
    alimentacion = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    mascotas = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Mascotas", color_hex="#16A34A")
    )

    servicio.asignar_categoria(usuario.id, comercio.id, alimentacion.id)
    servicio.asignar_categoria(usuario.id, comercio.id, mascotas.id)

    assert servicio.categoria_sugerida_para(usuario.id, comercio.id) == mascotas.id


def test_asignar_categoria_no_deja_usar_una_categoria_padre(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario
) -> None:
    comercio = servicio.resolver_o_crear("Walmart San Sebastián")
    padre = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    categorias.crear(
        CrearCategoriaComando(
            usuario_id=usuario.id,
            nombre="Supermercado",
            color_hex="#16A34A",
            categoria_padre_id=padre.id,
        )
    )

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.asignar_categoria(usuario.id, comercio.id, padre.id)


def test_asignar_categoria_de_otro_titular_falla(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    comercio = servicio.resolver_o_crear("Walmart San Sebastián")
    categoria_ajena = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-comercio@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()

    with pytest.raises(RecursoNoEncontrado):
        servicio.asignar_categoria(otro.id, comercio.id, categoria_ajena.id)


def test_asignar_categoria_a_un_comercio_inexistente_falla(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    with pytest.raises(RecursoNoEncontrado):
        servicio.asignar_categoria(usuario.id, 9999, categoria.id)


def test_clasificar_agrupa_por_comercio_y_moneda(
    servicio: ComercioService, usuario: Usuario
) -> None:
    comprobantes = [
        _comprobante(comercio="WALMART", monto=Decimal("100.00")),
        _comprobante(comercio="WALMART", monto=Decimal("50.00")),
        _comprobante(comercio="AUTOMERCADO", monto=Decimal("30.00")),
    ]

    clasificados = servicio.clasificar_comprobantes(usuario.id, comprobantes)

    por_nombre = {c.nombre: c for c in clasificados}
    assert por_nombre["WALMART"].total == Decimal("150.00")
    assert por_nombre["WALMART"].cantidad_transacciones == 2
    assert por_nombre["AUTOMERCADO"].total == Decimal("30.00")


def test_clasificar_no_mezcla_monedas_del_mismo_comercio(
    servicio: ComercioService, usuario: Usuario
) -> None:
    comprobantes = [
        _comprobante(comercio="AMAZON", moneda="USD", monto=Decimal("20.00")),
        _comprobante(comercio="AMAZON", moneda="CRC", monto=Decimal("5000.00")),
    ]

    clasificados = servicio.clasificar_comprobantes(usuario.id, comprobantes)

    assert len(clasificados) == 2
    por_moneda = {c.moneda: c.total for c in clasificados}
    assert por_moneda == {"USD": Decimal("20.00"), "CRC": Decimal("5000.00")}


def test_clasificar_descarta_lo_que_no_es_una_compra_confiable(
    servicio: ComercioService, usuario: Usuario
) -> None:
    comprobantes = [
        _comprobante(tipo_transaccion="TRANSFERENCIA"),
        _comprobante(confianza=0.4),
        _comprobante(comercio=None),
    ]

    assert servicio.clasificar_comprobantes(usuario.id, comprobantes) == []


def test_clasificar_adjunta_la_categoria_sugerida_si_existe(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario
) -> None:
    comercio = servicio.resolver_o_crear("WALMART")
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)

    clasificados = servicio.clasificar_comprobantes(usuario.id, [_comprobante(comercio="WALMART")])

    assert len(clasificados) == 1
    assert clasificados[0].categoria_id == categoria.id
    assert clasificados[0].categoria_nombre == "Alimentación"


def test_clasificar_sin_categoria_asignada_devuelve_none(
    servicio: ComercioService, usuario: Usuario
) -> None:
    clasificados = servicio.clasificar_comprobantes(usuario.id, [_comprobante(comercio="WALMART")])

    assert clasificados[0].categoria_id is None
    assert clasificados[0].categoria_nombre is None


def test_clasificar_no_filtra_la_categoria_de_otro_titular(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    """La sugerencia de un titular no se le aplica a otro que compra en el mismo comercio."""
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-clasificar@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()

    comercio = servicio.resolver_o_crear("WALMART")
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)

    clasificados = servicio.clasificar_comprobantes(otro.id, [_comprobante(comercio="WALMART")])

    assert clasificados[0].categoria_id is None


# ---- detallar_comprobantes ----


def test_detallar_no_agrupa_conserva_un_renglon_por_comprobante(
    servicio: ComercioService, usuario: Usuario
) -> None:
    comprobantes = [
        _comprobante(comercio="WALMART", monto=Decimal("100.00")),
        _comprobante(comercio="WALMART", monto=Decimal("50.00")),
    ]

    detalle = servicio.detallar_comprobantes(usuario.id, comprobantes)

    assert len(detalle) == 2
    assert {m.monto for m in detalle} == {Decimal("100.00"), Decimal("50.00")}


def test_detallar_conserva_autorizacion_y_referencia(
    servicio: ComercioService, usuario: Usuario
) -> None:
    detalle = servicio.detallar_comprobantes(usuario.id, [_comprobante()])

    assert len(detalle) == 1
    assert detalle[0].autorizacion == "1"
    assert detalle[0].referencia == "1"
    assert detalle[0].marca_tarjeta == "VISA"
    assert detalle[0].ultimos_cuatro == "1234"
    assert detalle[0].banco == "BAC Credomatic"


def test_detallar_adjunta_la_categoria_sugerida(
    servicio: ComercioService, categorias: CategoriaService, usuario: Usuario
) -> None:
    comercio = servicio.resolver_o_crear("WALMART")
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    servicio.asignar_categoria(usuario.id, comercio.id, categoria.id)

    detalle = servicio.detallar_comprobantes(usuario.id, [_comprobante(comercio="WALMART")])

    assert detalle[0].categoria_nombre == "Alimentación"


def test_detallar_descarta_lo_que_no_es_una_compra_confiable(
    servicio: ComercioService, usuario: Usuario
) -> None:
    comprobantes = [
        _comprobante(tipo_transaccion="TRANSFERENCIA"),
        _comprobante(confianza=0.4),
        _comprobante(comercio=None),
        _comprobante(monto=None),
    ]

    assert servicio.detallar_comprobantes(usuario.id, comprobantes) == []


def test_detallar_ordena_del_mas_reciente_al_mas_viejo(
    servicio: ComercioService, usuario: Usuario
) -> None:
    viejo = ComprobanteParseado(
        banco="BAC Credomatic",
        comercio="A",
        ciudad=None,
        pais=None,
        fecha=datetime(2026, 1, 1),
        marca_tarjeta="VISA",
        ultimos_cuatro="1234",
        autorizacion="1",
        referencia="1",
        tipo_transaccion="COMPRA",
        moneda="CRC",
        monto=Decimal("10"),
        confianza=1.0,
    )
    reciente = ComprobanteParseado(
        banco="BAC Credomatic",
        comercio="B",
        ciudad=None,
        pais=None,
        fecha=datetime(2026, 8, 1),
        marca_tarjeta="VISA",
        ultimos_cuatro="1234",
        autorizacion="1",
        referencia="1",
        tipo_transaccion="COMPRA",
        moneda="CRC",
        monto=Decimal("20"),
        confianza=1.0,
    )

    detalle = servicio.detallar_comprobantes(usuario.id, [viejo, reciente])

    assert [m.comercio for m in detalle] == ["B", "A"]
