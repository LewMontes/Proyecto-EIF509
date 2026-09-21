"""Reglas de negocio de las reglas de categorización, probadas sin pasar por HTTP."""

import pytest
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.services.categoria_service import CategoriaService, CrearCategoriaComando
from app.business.services.regla_categorizacion_service import (
    CrearReglaComando,
    ReglaCategorizacionService,
)
from app.data.models.categoria import Categoria
from app.data.models.enums import CampoRegla, Moneda
from app.data.models.usuario import Usuario
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.usuario_repository import UsuarioRepository


@pytest.fixture
def servicio(sesion: Session) -> ReglaCategorizacionService:
    return ReglaCategorizacionService(
        ReglaCategorizacionRepository(sesion),
        CategoriaRepository(sesion),
        UsuarioRepository(sesion),
    )


@pytest.fixture
def categorias(sesion: Session) -> CategoriaService:
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


@pytest.fixture
def categoria(categorias: CategoriaService, usuario: Usuario) -> Categoria:
    return categorias.crear(
        CrearCategoriaComando(usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E")
    )


def test_crea_una_regla_con_prioridad_automatica(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    regla = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Walmart es supermercado",
            patron="WALMART",
            categoria_destino_id=categoria.id,
        )
    )

    assert regla.id is not None
    assert regla.activa is True
    assert regla.veces_aplicada == 0
    assert regla.prioridad == 1


def test_dos_reglas_sin_prioridad_explicita_no_chocan(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    primera = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Regla A",
            patron="WALMART",
            categoria_destino_id=categoria.id,
        )
    )
    segunda = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Regla B",
            patron="MAXIPALI",
            categoria_destino_id=categoria.id,
        )
    )

    assert segunda.prioridad == primera.prioridad + 1


def test_rechaza_nombre_vacio(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="   ",
                patron="WALMART",
                categoria_destino_id=categoria.id,
            )
        )


def test_rechaza_patron_vacio(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="Regla",
                patron="  ",
                categoria_destino_id=categoria.id,
            )
        )


def test_rechaza_nombre_repetido(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Regla",
            patron="WALMART",
            categoria_destino_id=categoria.id,
        )
    )

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="regla",
                patron="MAXIPALI",
                categoria_destino_id=categoria.id,
            )
        )


def test_rechaza_prioridad_repetida(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Regla A",
            patron="WALMART",
            categoria_destino_id=categoria.id,
            prioridad=5,
        )
    )

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="Regla B",
                patron="MAXIPALI",
                categoria_destino_id=categoria.id,
                prioridad=5,
            )
        )


def test_rechaza_categoria_de_otro_titular(
    servicio: ReglaCategorizacionService, usuario: Usuario, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-regla@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    categoria_ajena = CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    ).crear(CrearCategoriaComando(usuario_id=otro.id, nombre="Ajena", color_hex="#22C55E"))

    with pytest.raises(RecursoNoEncontrado):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="Regla",
                patron="WALMART",
                categoria_destino_id=categoria_ajena.id,
            )
        )


def test_rechaza_categoria_que_no_es_hoja(
    servicio: ReglaCategorizacionService,
    categorias: CategoriaService,
    usuario: Usuario,
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

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="Regla",
                patron="WALMART",
                categoria_destino_id=grupo.id,
            )
        )


def test_rechaza_campo_no_soportado(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearReglaComando(
                usuario_id=usuario.id,
                nombre="Regla",
                patron="WALMART",
                categoria_destino_id=categoria.id,
                campo=CampoRegla.DESCRIPCION_LINEA,
            )
        )


def test_lista_solo_las_reglas_del_titular(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-regla-listar@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    categoria_ajena = CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    ).crear(CrearCategoriaComando(usuario_id=otro.id, nombre="Ajena", color_hex="#22C55E"))
    servicio.crear(
        CrearReglaComando(
            usuario_id=otro.id,
            nombre="Ajena",
            patron="WALMART",
            categoria_destino_id=categoria_ajena.id,
        )
    )
    propia = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Propia",
            patron="WALMART",
            categoria_destino_id=categoria.id,
        )
    )

    assert [r.id for r in servicio.listar(usuario.id)] == [propia.id]


def test_desactivar_no_borra(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria
) -> None:
    regla = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Regla",
            patron="WALMART",
            categoria_destino_id=categoria.id,
        )
    )

    desactivada = servicio.desactivar(usuario.id, regla.id)

    assert desactivada.activa is False
    assert servicio.listar(usuario.id) == [desactivada]


def test_desactivar_de_otro_titular_falla(
    servicio: ReglaCategorizacionService, usuario: Usuario, categoria: Categoria, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-regla-desactivar@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    regla = servicio.crear(
        CrearReglaComando(
            usuario_id=usuario.id,
            nombre="Regla",
            patron="WALMART",
            categoria_destino_id=categoria.id,
        )
    )

    with pytest.raises(RecursoNoEncontrado):
        servicio.desactivar(otro.id, regla.id)
