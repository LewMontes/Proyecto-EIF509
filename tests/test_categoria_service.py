"""Reglas de negocio de las categorias, probadas sin pasar por HTTP."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.services.categoria_service import CategoriaService, CrearCategoriaComando
from app.data.models.categoria_estandar import CategoriaEstandar
from app.data.models.enums import Moneda
from app.data.models.usuario import Usuario
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.usuario_repository import UsuarioRepository


@pytest.fixture
def servicio(sesion: Session) -> CategoriaService:
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


def _sembrar_taxonomia_de_prueba(sesion: Session) -> None:
    """Un subconjunto chico de `categoria_estandar` -alcanza para probar la
    jerarquía sin repetir las 15 filas reales de `database.py`."""
    sesion.add_all(
        [
            CategoriaEstandar(
                codigo="ALIMENTACION", nombre="Alimentacion", color_hex="#16A34A", orden=1
            ),
            CategoriaEstandar(
                codigo="SUPERMERCADO", nombre="Supermercado", color_hex="#22C55E", orden=2
            ),
            CategoriaEstandar(
                codigo="RESTAURANTES", nombre="Restaurantes y sodas", color_hex="#4ADE80", orden=3
            ),
            CategoriaEstandar(codigo="OTROS", nombre="Otros", color_hex="#6B7280", orden=15),
        ]
    )
    sesion.commit()


def test_crea_una_categoria_hoja_y_activa(servicio: CategoriaService, usuario: Usuario) -> None:
    categoria = servicio.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentacion", color_hex="#2563eb")
    )

    assert categoria.id is not None
    assert categoria.es_hoja is True
    assert categoria.activa is True
    assert categoria.color_hex == "#2563EB", "el color se normaliza a mayusculas"


def test_colgar_una_subcategoria_convierte_a_la_padre_en_totalizadora(
    servicio: CategoriaService, usuario: Usuario
) -> None:
    padre = servicio.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentacion", color_hex="#2563EB")
    )

    hija = servicio.crear(
        CrearCategoriaComando(
            usuario_id=usuario.id,
            nombre="Supermercado",
            color_hex="#16A34A",
            categoria_padre_id=padre.id,
        )
    )

    assert padre.es_hoja is False, "las categorias padre totalizan, no reciben gasto directo"
    assert hija.es_hoja is True
    assert hija.categoria_padre_id == padre.id


def test_rechaza_un_nombre_repetido_en_la_misma_cuenta(
    servicio: CategoriaService, usuario: Usuario
) -> None:
    servicio.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentacion", color_hex="#2563EB")
    )

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearCategoriaComando(usuario_id=usuario.id, nombre="alimentacion", color_hex="#111111")
        )


def test_rechaza_un_color_que_no_es_hexadecimal(
    servicio: CategoriaService, usuario: Usuario
) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.crear(
            CrearCategoriaComando(usuario_id=usuario.id, nombre="Transporte", color_hex="azul")
        )


def test_rechaza_un_nombre_en_blanco(servicio: CategoriaService, usuario: Usuario) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.crear(
            CrearCategoriaComando(usuario_id=usuario.id, nombre="   ", color_hex="#2563EB")
        )


def test_no_deja_colgar_una_categoria_de_la_padre_de_otra_cuenta(
    servicio: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    ajena = servicio.crear(
        CrearCategoriaComando(usuario_id=otro.id, nombre="Alimentacion", color_hex="#2563EB")
    )

    with pytest.raises(RecursoNoEncontrado):
        servicio.crear(
            CrearCategoriaComando(
                usuario_id=usuario.id,
                nombre="Supermercado",
                color_hex="#16A34A",
                categoria_padre_id=ajena.id,
            )
        )


def test_rechaza_un_usuario_que_no_existe(servicio: CategoriaService) -> None:
    with pytest.raises(RecursoNoEncontrado):
        servicio.crear(
            CrearCategoriaComando(usuario_id=9999, nombre="Alimentacion", color_hex="#2563EB")
        )


def test_lista_solo_las_categorias_activas_del_titular(
    servicio: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    activa = servicio.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Alimentacion", color_hex="#2563EB")
    )
    desactivada = servicio.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Mascotas", color_hex="#F59E0B")
    )
    desactivada.activa = False
    sesion.commit()

    listadas = servicio.listar_activas(usuario.id)

    assert [categoria.id for categoria in listadas] == [activa.id]


# ---- sembrar_estandar ----


def test_sembrar_estandar_arma_la_jerarquia(
    servicio: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    _sembrar_taxonomia_de_prueba(sesion)

    creadas = servicio.sembrar_estandar(usuario.id)
    por_nombre = {c.nombre: c for c in creadas}

    assert len(creadas) == 4
    assert por_nombre["Alimentacion"].es_hoja is False, "tiene hijas: totaliza, no recibe gasto"
    assert por_nombre["Alimentacion"].categoria_padre_id is None
    assert por_nombre["Supermercado"].categoria_padre_id == por_nombre["Alimentacion"].id
    assert por_nombre["Restaurantes y sodas"].categoria_padre_id == por_nombre["Alimentacion"].id
    assert por_nombre["Otros"].es_hoja is True, "sin hijas: queda suelta como hoja"
    assert por_nombre["Otros"].categoria_padre_id is None
    for categoria in creadas:
        assert categoria.categoria_estandar_id is not None


def test_sembrar_estandar_sin_taxonomia_global_no_crea_nada(
    servicio: CategoriaService, usuario: Usuario
) -> None:
    """Una base nueva antes de que corra `sembrar_categorias_estandar()` -no es
    un error, la cuenta arranca sin catálogo semilla y puede crear categorías
    a mano, como antes de que existiera esta función."""
    assert servicio.sembrar_estandar(usuario.id) == []
    assert servicio.listar_activas(usuario.id) == []


def test_sembrar_estandar_dos_veces_choca_con_el_nombre_ya_sembrado(
    servicio: CategoriaService, usuario: Usuario, sesion: Session
) -> None:
    """Documenta el límite real: `sembrar_estandar` no es idempotente por sí
    sola -se apoya en que `AuthService.registrar` la llama una sola vez, justo
    al crear la cuenta- `uq_categoria_usuario_nombre` es lo que evita que una
    doble siembra deje nombres repetidos, aunque lo haga con un error en vez
    de en silencio."""
    _sembrar_taxonomia_de_prueba(sesion)
    servicio.sembrar_estandar(usuario.id)

    with pytest.raises(IntegrityError):
        servicio.sembrar_estandar(usuario.id)
