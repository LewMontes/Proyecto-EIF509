"""Reglas de negocio de los presupuestos, sin tocar red."""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.services.categoria_service import CategoriaService, CrearCategoriaComando
from app.business.services.presupuesto_service import PresupuestoService
from app.data.models.enums import EstadoPresupuesto, Moneda
from app.data.models.usuario import Usuario
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.usuario_repository import UsuarioRepository


@pytest.fixture
def servicio(sesion: Session) -> PresupuestoService:
    return PresupuestoService(
        PresupuestoRepository(sesion), CategoriaRepository(sesion), UsuarioRepository(sesion)
    )


@pytest.fixture
def categorias(sesion: Session) -> CategoriaService:
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


# ---- calcular_estado: función pura ----


def test_calcular_estado_en_rango() -> None:
    porcentaje, estado = PresupuestoService.calcular_estado(
        Decimal("50"), Decimal("200"), umbral_alerta=80
    )
    assert porcentaje == 25.0
    assert estado == EstadoPresupuesto.EN_RANGO


def test_calcular_estado_cerca_del_limite_en_el_umbral_exacto() -> None:
    porcentaje, estado = PresupuestoService.calcular_estado(
        Decimal("80"), Decimal("100"), umbral_alerta=80
    )
    assert porcentaje == 80.0
    assert estado == EstadoPresupuesto.CERCA_DEL_LIMITE


def test_calcular_estado_excedido() -> None:
    porcentaje, estado = PresupuestoService.calcular_estado(
        Decimal("150"), Decimal("100"), umbral_alerta=80
    )
    assert porcentaje == 150.0
    assert estado == EstadoPresupuesto.EXCEDIDO


def test_calcular_estado_con_limite_cero_no_revienta() -> None:
    porcentaje, estado = PresupuestoService.calcular_estado(
        Decimal("10"), Decimal("0"), umbral_alerta=80
    )
    assert porcentaje == 0.0
    assert estado == EstadoPresupuesto.EN_RANGO


# ---- crear_o_actualizar ----


def test_crear_presupuesto(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    presupuesto = servicio.crear_o_actualizar(
        usuario_id=usuario.id,
        categoria_id=categoria.id,
        anio=2026,
        mes=8,
        moneda=Moneda.CRC,
        monto_limite=Decimal("220000"),
    )

    assert presupuesto.id is not None
    assert presupuesto.umbral_alerta == 80


def test_crear_dos_veces_el_mismo_periodo_corrige_en_vez_de_duplicar(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    primero = servicio.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("200000")
    )
    segundo = servicio.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("250000")
    )

    assert primero.id == segundo.id
    assert len(servicio.listar_del_periodo(usuario.id, 2026, 8)) == 1
    assert servicio.listar_del_periodo(usuario.id, 2026, 8)[0].monto_limite == Decimal("250000")


def test_crear_presupuesto_con_limite_negativo_falla(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    with pytest.raises(DatosInvalidos):
        servicio.crear_o_actualizar(usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("-1"))


def test_crear_presupuesto_con_mes_invalido_falla(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    with pytest.raises(DatosInvalidos):
        servicio.crear_o_actualizar(usuario.id, categoria.id, 2026, 13, Moneda.CRC, Decimal("100"))


def test_crear_presupuesto_en_una_categoria_padre_falla(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
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
        servicio.crear_o_actualizar(usuario.id, padre.id, 2026, 8, Moneda.CRC, Decimal("100"))


def test_crear_presupuesto_en_categoria_de_otro_titular_falla(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-presupuesto@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    categoria_ajena = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )

    with pytest.raises(RecursoNoEncontrado):
        servicio.crear_o_actualizar(
            otro.id, categoria_ajena.id, 2026, 8, Moneda.CRC, Decimal("100")
        )


def test_eliminar_presupuesto(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    presupuesto = servicio.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("100000")
    )

    servicio.eliminar(usuario.id, presupuesto.id)

    assert servicio.listar_del_periodo(usuario.id, 2026, 8) == []


def test_eliminar_presupuesto_de_otro_titular_falla(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-eliminar@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    presupuesto = servicio.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("100000")
    )

    with pytest.raises(RecursoNoEncontrado):
        servicio.eliminar(otro.id, presupuesto.id)


# ---- calcular_estados: lee el consumo ya acumulado ----
#
# `monto_consumido` ya no se recalcula acá desde comercios clasificados: lo
# acumula `ConciliacionService` dentro de la transacción que registra cada
# compra real (ver test_conciliacion_service.py). Estas pruebas verifican
# que `calcular_estados` lee ese valor y calcula bien el porcentaje/estado
# -mutan `monto_consumido` directo, como si ya lo hubiera acumulado una
# conciliación real.


def test_calcular_estados_lee_el_consumo_ya_acumulado(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    presupuesto = servicio.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("100000")
    )
    presupuesto.monto_consumido = Decimal("50000")
    sesion.commit()

    estados = servicio.calcular_estados(usuario.id, 2026, 8)

    assert len(estados) == 1
    assert estados[0].monto_consumido == Decimal("50000")
    assert estados[0].estado == EstadoPresupuesto.EN_RANGO


def test_calcular_estados_sin_acumular_nada_da_cero(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    servicio.crear_o_actualizar(usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("100000"))

    estados = servicio.calcular_estados(usuario.id, 2026, 8)

    assert estados[0].monto_consumido == Decimal("0")


def test_calcular_estados_sin_presupuestos_del_periodo_devuelve_vacio(
    servicio: PresupuestoService, usuario: Usuario
) -> None:
    assert servicio.calcular_estados(usuario.id, 2026, 8) == []


def test_calcular_estados_marca_excedido_con_el_consumo_acumulado(
    servicio: PresupuestoService, categorias: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    categoria = categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentación", color_hex="#2563EB")
    )
    presupuesto = servicio.crear_o_actualizar(
        usuario.id, categoria.id, 2026, 8, Moneda.CRC, Decimal("50000"), umbral_alerta=80
    )
    presupuesto.monto_consumido = Decimal("60000")
    sesion.commit()

    estados = servicio.calcular_estados(usuario.id, 2026, 8)

    assert estados[0].estado == EstadoPresupuesto.EXCEDIDO
    assert estados[0].porcentaje_usado == 120.0
