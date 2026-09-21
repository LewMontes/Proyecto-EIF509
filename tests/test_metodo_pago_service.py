"""Reglas de negocio de los métodos de pago, probadas sin pasar por HTTP."""

import pytest
from sqlalchemy.orm import Session

from app.business.errors import DatosInvalidos, RecursoNoEncontrado, ReglaDeNegocioViolada
from app.business.services.metodo_pago_service import CrearMetodoPagoComando, MetodoPagoService
from app.data.models.enums import Moneda, TipoMetodoPago
from app.data.models.usuario import Usuario
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.usuario_repository import UsuarioRepository


@pytest.fixture
def servicio(sesion: Session) -> MetodoPagoService:
    return MetodoPagoService(MetodoPagoRepository(sesion), UsuarioRepository(sesion))


def test_crea_una_tarjeta_de_credito(servicio: MetodoPagoService, usuario: Usuario) -> None:
    metodo_pago = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id,
            alias="Visa BAC",
            tipo=TipoMetodoPago.CREDITO,
            ultimos_cuatro="4321",
            entidad="BAC",
            dia_corte=15,
        )
    )

    assert metodo_pago.id is not None
    assert metodo_pago.activo is True
    assert metodo_pago.ultimos_cuatro == "4321"


def test_crea_efectivo_sin_ultimos_cuatro(servicio: MetodoPagoService, usuario: Usuario) -> None:
    metodo_pago = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO
        )
    )

    assert metodo_pago.ultimos_cuatro is None


def test_rechaza_ultimos_cuatro_en_efectivo(servicio: MetodoPagoService, usuario: Usuario) -> None:
    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearMetodoPagoComando(
                usuario_id=usuario.id,
                alias="Efectivo",
                tipo=TipoMetodoPago.EFECTIVO,
                ultimos_cuatro="0000",
            )
        )


def test_rechaza_ultimos_cuatro_que_no_son_cuatro_digitos(
    servicio: MetodoPagoService, usuario: Usuario
) -> None:
    with pytest.raises(DatosInvalidos):
        servicio.crear(
            CrearMetodoPagoComando(
                usuario_id=usuario.id,
                alias="Visa",
                tipo=TipoMetodoPago.DEBITO,
                ultimos_cuatro="12",
            )
        )


def test_rechaza_dos_tarjetas_con_los_mismos_ultimos_cuatro(
    servicio: MetodoPagoService, usuario: Usuario
) -> None:
    servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id,
            alias="Visa BAC",
            tipo=TipoMetodoPago.CREDITO,
            ultimos_cuatro="4321",
        )
    )

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearMetodoPagoComando(
                usuario_id=usuario.id,
                alias="Visa BN",
                tipo=TipoMetodoPago.DEBITO,
                ultimos_cuatro="4321",
            )
        )


def test_rechaza_dia_de_corte_fuera_de_credito(
    servicio: MetodoPagoService, usuario: Usuario
) -> None:
    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearMetodoPagoComando(
                usuario_id=usuario.id,
                alias="Visa BAC",
                tipo=TipoMetodoPago.DEBITO,
                ultimos_cuatro="4321",
                dia_corte=15,
            )
        )


def test_rechaza_alias_repetido(servicio: MetodoPagoService, usuario: Usuario) -> None:
    servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO
        )
    )

    with pytest.raises(ReglaDeNegocioViolada):
        servicio.crear(
            CrearMetodoPagoComando(
                usuario_id=usuario.id, alias="efectivo", tipo=TipoMetodoPago.SINPE_MOVIL
            )
        )


def test_lista_solo_los_metodos_del_titular(
    servicio: MetodoPagoService, usuario: Usuario, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-metodo-pago@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    servicio.crear(
        CrearMetodoPagoComando(usuario_id=otro.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO)
    )
    propio = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO
        )
    )

    listados = servicio.listar(usuario.id)

    assert [m.id for m in listados] == [propio.id]


def test_desactivar_no_borra(servicio: MetodoPagoService, usuario: Usuario) -> None:
    metodo_pago = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO
        )
    )

    desactivado = servicio.desactivar(usuario.id, metodo_pago.id)

    assert desactivado.activo is False
    assert servicio.listar(usuario.id) == [desactivado]


def test_desactivar_de_otro_titular_falla(
    servicio: MetodoPagoService, usuario: Usuario, sesion: Session
) -> None:
    otro = Usuario(
        nombre_completo="Otra persona",
        correo="otra-desactivar@gastonomo.cr",
        contrasena_hash="hash",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.commit()
    metodo_pago = servicio.crear(
        CrearMetodoPagoComando(
            usuario_id=usuario.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO
        )
    )

    with pytest.raises(RecursoNoEncontrado):
        servicio.desactivar(otro.id, metodo_pago.id)
