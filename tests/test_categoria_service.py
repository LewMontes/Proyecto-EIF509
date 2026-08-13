"""Pruebas de las reglas de negocio de las categorias."""

import pytest
from sqlalchemy.orm import Session

from app.business.errors import RecursoNoEncontrado, ReglaDeNegocioViolada, ValidacionFallida
from app.business.services.categoria_service import CategoriaService, CrearCategoriaComando
from app.data.models import Usuario
from app.data.repositories.categoria_repository import CategoriaRepository


@pytest.fixture
def servicio(session: Session) -> CategoriaService:
    return CategoriaService(CategoriaRepository(session))


class TestCreacion:
    def test_crea_una_categoria_raiz(self, servicio, usuario):
        categoria = servicio.crear(CrearCategoriaComando(usuario.id, "Alimentacion"))

        assert categoria.id is not None
        assert categoria.nombre == "Alimentacion"
        assert categoria.es_hoja is True

    def test_recorta_espacios_del_nombre(self, servicio, usuario):
        categoria = servicio.crear(CrearCategoriaComando(usuario.id, "  Transporte  "))

        assert categoria.nombre == "Transporte"

    def test_normaliza_el_color_a_mayusculas(self, servicio, usuario):
        categoria = servicio.crear(CrearCategoriaComando(usuario.id, "Salud", color_hex="#a1b2c3"))

        assert categoria.color_hex == "#A1B2C3"


class TestValidaciones:
    def test_rechaza_nombre_vacio(self, servicio, usuario):
        with pytest.raises(ValidacionFallida, match="vacio"):
            servicio.crear(CrearCategoriaComando(usuario.id, "   "))

    def test_rechaza_color_sin_numeral(self, servicio, usuario):
        with pytest.raises(ValidacionFallida, match="hexadecimal"):
            servicio.crear(CrearCategoriaComando(usuario.id, "Ocio", color_hex="2563EBB"))

    def test_rechaza_color_no_hexadecimal(self, servicio, usuario):
        with pytest.raises(ValidacionFallida, match="hexadecimal"):
            servicio.crear(CrearCategoriaComando(usuario.id, "Ocio", color_hex="#ZZZZZZ"))


class TestNombreUnico:
    def test_rechaza_nombre_repetido_del_mismo_usuario(self, servicio, usuario):
        servicio.crear(CrearCategoriaComando(usuario.id, "Alimentacion"))

        with pytest.raises(ReglaDeNegocioViolada, match="Ya existe"):
            servicio.crear(CrearCategoriaComando(usuario.id, "Alimentacion"))

    def test_permite_el_mismo_nombre_en_otro_usuario(self, servicio, usuario, session):
        otro = Usuario(nombre_completo="Otra persona", correo="otra@est.una.ac.cr")
        session.add(otro)
        session.commit()

        servicio.crear(CrearCategoriaComando(usuario.id, "Alimentacion"))
        categoria = servicio.crear(CrearCategoriaComando(otro.id, "Alimentacion"))

        assert categoria.usuario_id == otro.id


class TestJerarquia:
    def test_la_padre_deja_de_ser_hoja(self, servicio, usuario):
        padre = servicio.crear(CrearCategoriaComando(usuario.id, "Alimentacion"))

        servicio.crear(
            CrearCategoriaComando(usuario.id, "Supermercado", categoria_padre_id=padre.id)
        )

        assert padre.es_hoja is False

    def test_rechaza_padre_inexistente(self, servicio, usuario):
        with pytest.raises(RecursoNoEncontrado):
            servicio.crear(
                CrearCategoriaComando(usuario.id, "Supermercado", categoria_padre_id=999)
            )

    def test_rechaza_padre_de_otro_usuario(self, servicio, usuario, session):
        otro = Usuario(nombre_completo="Otra persona", correo="otra@est.una.ac.cr")
        session.add(otro)
        session.commit()
        ajena = servicio.crear(CrearCategoriaComando(otro.id, "Alimentacion"))

        # Pasar un id ajeno no debe dejar colgar una categoria del arbol de otra persona.
        with pytest.raises(RecursoNoEncontrado):
            servicio.crear(
                CrearCategoriaComando(usuario.id, "Supermercado", categoria_padre_id=ajena.id)
            )
