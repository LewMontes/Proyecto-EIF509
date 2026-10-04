"""La transacción del Proceso 2, con un fallo provocado a mitad de camino.

`test_esquema_postgres.py` ya prueba que el `ROLLBACK` de PostgreSQL deshace
varias escrituras pendientes; eso verifica el **motor**. Estas dos pruebas
verifican el **servicio**: que `ConciliacionService.conciliar` de verdad deje
sus cinco escrituras dentro de una sola transacción, provocando el fallo en
mitad del proceso y comprobando después, contra la base, que no quedó nada.

Es la garantía que el dominio declara como razón de ser de la transacción (ver
`docs/propuesta-dominio.md`, «Por qué es transaccional»): si el paso del
presupuesto falla, no puede quedar un comprobante marcado como conciliado y
una compra creada que nunca impactó el avance mensual. Como el comprobante ya
quedaría ligado a una compra, un reintento no lo volvería a tomar y la
inconsistencia sería permanente.

El fallo se provoca con `unittest.mock.patch.object` sobre el repositorio que
el paso usa -no ensuciando la base ni tocando el servicio- para que sea el
servicio real, sin modificar, el que corre.

Corren contra un `postgres:16-alpine` real y no sobre SQLite a propósito: una
transacción que se revierte es justo lo que esta aplicación depende del motor
de verdad, y las pruebas del resto de la suite comparten una sesión SQLite en
memoria donde el `ROLLBACK` no cuesta lo mismo.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.comercio_service import ComercioService
from app.business.services.conciliacion_service import (
    ConciliacionService,
    ConciliarComprobanteComando,
)
from app.data.models.categoria import Categoria
from app.data.models.comercio import Comercio
from app.data.models.compra import Compra
from app.data.models.comprobante import Comprobante
from app.data.models.cuenta_correo import CuentaCorreo
from app.data.models.enums import (
    CampoRegla,
    EstadoComprobante,
    EstadoCuentaCorreo,
    Moneda,
    ProveedorCorreo,
    TipoMetodoPago,
)
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.models.presupuesto import Presupuesto
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.models.usuario import Usuario
from app.data.repositories.bitacora_repository import BitacoraRepository
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

pytestmark = pytest.mark.integracion

FECHA_DE_LA_COMPRA = datetime(2026, 8, 30, 13, 27)
MONTO = Decimal("7870.00")


class _Escenario:
    """Todo lo que la conciliación va a tocar, ya guardado y confirmado.

    Se confirma en el constructor a propósito: lo que estas pruebas verifican
    es que el `ROLLBACK` deshaga lo que escribe **la conciliación**, no lo que
    preparó la prueba. Si el escenario quedara pendiente en la misma
    transacción, el rollback se lo llevaría también y las comprobaciones no
    demostrarían nada.
    """

    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion
        self.usuario = Usuario(
            nombre_completo="Titular de prueba",
            correo="titular@gastonomo.cr",
            contrasena_hash="hash-de-prueba-con-el-largo-minimo",
        )
        sesion.add(self.usuario)
        sesion.flush()

        self.categoria = Categoria(
            usuario_id=self.usuario.id,
            nombre="Supermercado",
            color_hex="#2563EB",
            es_hoja=True,
            activa=True,
        )
        sesion.add(self.categoria)
        sesion.flush()

        self.metodo_pago = MetodoPago(
            usuario_id=self.usuario.id,
            alias="Visa BAC",
            tipo=TipoMetodoPago.CREDITO,
            moneda=Moneda.CRC,
            ultimos_cuatro="4321",
            activo=True,
        )
        self.regla = ReglaCategorizacion(
            usuario_id=self.usuario.id,
            categoria_destino_id=self.categoria.id,
            nombre="Supermercados",
            campo=CampoRegla.COMERCIO_NORMALIZADO,
            patron="WALMART",
            prioridad=1,
            activa=True,
            veces_aplicada=0,
        )
        self.presupuesto = Presupuesto(
            usuario_id=self.usuario.id,
            categoria_id=self.categoria.id,
            anio=FECHA_DE_LA_COMPRA.year,
            mes=FECHA_DE_LA_COMPRA.month,
            moneda=Moneda.CRC,
            monto_limite=Decimal("200000.00"),
            monto_consumido=Decimal("0.00"),
            umbral_alerta=80,
        )
        cuenta = CuentaCorreo(
            usuario_id=self.usuario.id,
            proveedor=ProveedorCorreo.OUTLOOK,
            direccion="titular@hotmail.com",
            token_acceso_cifrado="cifrado",
            token_refresco_cifrado="cifrado",
            expira_en=datetime.now(UTC),
            estado=EstadoCuentaCorreo.ACTIVA,
        )
        sesion.add_all([self.metodo_pago, self.regla, self.presupuesto, cuenta])
        sesion.flush()

        self.comprobante = Comprobante(
            usuario_id=self.usuario.id,
            cuenta_correo_id=cuenta.id,
            mensaje_id="mensaje-1",
            remitente="notificacion@baccredomatic.cr",
            banco="BAC Credomatic",
            confianza=1.0,
        )
        sesion.add(self.comprobante)
        sesion.commit()

    @property
    def comando(self) -> ConciliarComprobanteComando:
        """La orden de conciliar: lo que el lector extrajo, no la entidad."""
        return ConciliarComprobanteComando(
            usuario_id=self.usuario.id,
            comprobante_id=self.comprobante.id,
            comercio="Walmart San Sebastián",
            monto=MONTO,
            moneda="CRC",
            fecha=FECHA_DE_LA_COMPRA,
            ultimos_cuatro="4321",
            tipo_transaccion="COMPRA",
            confianza=1.0,
        )


def _armar(sesion: Session) -> ConciliacionService:
    """La misma conciliación que arma `dependencies.py`, sin Mongo ni red."""
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
        None,
        BitacoraComprasService(BitacoraRepository(None)),
    )


def _contar(sesion: Session, entidad) -> int:
    return sesion.scalar(select(func.count()).select_from(entidad))


@pytest.fixture
def sesion_sin_transaccion_externa(motor_postgres: Engine) -> Iterator[Session]:
    """Una sesión con transacciones de verdad, no anidadas dentro de otra.

    El resto de las pruebas de integración corre dentro de una transacción
    que `conftest.py` revierte al terminar: es lo que permite compartir un
    contenedor entre todas sin recrear el esquema. Acá eso no sirve, porque
    lo que se prueba **es** el `commit` y el `rollback` del servicio: si
    estuvieran anidados en una transacción externa, el `rollback` de la
    prueba se llevaría también los datos del escenario y la comprobación no
    demostraría nada.

    Por eso esta fixture habla con el motor directo y limpia ella misma al
    final, en orden de dependencia.
    """
    fabrica = sessionmaker(bind=motor_postgres, autoflush=False, expire_on_commit=False)
    sesion = fabrica()
    try:
        yield sesion
    finally:
        sesion.rollback()
        for modelo in (
            LineaCompra,
            Comprobante,
            Compra,
            Presupuesto,
            ReglaCategorizacion,
            MetodoPago,
            Categoria,
            CuentaCorreo,
            Comercio,
            Usuario,
        ):
            sesion.execute(delete(modelo))
        sesion.commit()
        sesion.close()


@pytest.fixture
def escenario(sesion_sin_transaccion_externa: Session) -> _Escenario:
    return _Escenario(sesion_sin_transaccion_externa)


def test_un_fallo_al_acumular_el_presupuesto_no_deja_nada_escrito(
    sesion_sin_transaccion_externa: Session, escenario: _Escenario
) -> None:
    """El caso exacto que el dominio usa para justificar la transacción.

    Para cuando el paso 8 se ejecuta, la conciliación ya creó la `Compra`, su
    `LineaCompra` y subió el contador de la regla, y está a punto de marcar el
    comprobante. Si ese paso revienta, **ninguna** de esas escrituras puede
    sobrevivir: una compra sin impacto en el presupuesto, con el comprobante
    ya marcado como conciliado, sería una inconsistencia que ningún reintento
    podría corregir.
    """
    servicio = _armar(sesion_sin_transaccion_externa)

    with (
        patch.object(
            PresupuestoRepository,
            "buscar",
            side_effect=RuntimeError("caída al leer el presupuesto"),
        ),
        pytest.raises(RuntimeError),
    ):
        servicio.conciliar(escenario.comando)

    sesion_sin_transaccion_externa.rollback()

    assert _contar(sesion_sin_transaccion_externa, Compra) == 0, "la compra no debió quedar"
    assert _contar(sesion_sin_transaccion_externa, LineaCompra) == 0, "el renglón no debió quedar"

    comprobante = sesion_sin_transaccion_externa.scalars(
        select(Comprobante).where(Comprobante.id == escenario.comprobante.id)
    ).one()
    assert comprobante.compra_id is None, (
        "el comprobante no puede quedar conciliado: un reintento no lo volvería a tomar"
    )
    # Lo único que sí queda escrito, y a propósito fuera de la transacción
    # revertida: el intento fallido. Sigue PARSEADO, así que se puede reintentar.
    assert comprobante.estado == EstadoComprobante.PARSEADO
    assert comprobante.intentos_procesamiento == 1
    assert "caída al leer el presupuesto" in comprobante.motivo_fallo

    presupuesto = sesion_sin_transaccion_externa.scalars(
        select(Presupuesto).where(Presupuesto.id == escenario.presupuesto.id)
    ).one()
    assert presupuesto.monto_consumido == Decimal("0.00")

    regla = sesion_sin_transaccion_externa.scalars(
        select(ReglaCategorizacion).where(ReglaCategorizacion.id == escenario.regla.id)
    ).one()
    assert regla.veces_aplicada == 0, "el contador de la regla también es parte de la transacción"


def test_el_comercio_resuelto_sobrevive_al_rollback(
    sesion_sin_transaccion_externa: Session, escenario: _Escenario
) -> None:
    """La única escritura que queda **fuera** de la transacción, a propósito.

    `ComercioService.resolver_o_crear` confirma con su propio `commit`: el
    catálogo de comercios es compartido entre titulares y resolverlo es un
    paso previo a crear la compra, no parte de conciliar la de nadie en
    particular. Un comercio recién descubierto sigue siendo un comercio real
    aunque la conciliación que lo encontró se revierta -y dejarlo evita tener
    que volver a crearlo en el reintento.

    Esta prueba fija esa decisión para que un cambio futuro que meta el
    catálogo dentro de la transacción se note acá y no en producción.
    """
    servicio = _armar(sesion_sin_transaccion_externa)
    assert _contar(sesion_sin_transaccion_externa, Comercio) == 0

    with (
        patch.object(
            PresupuestoRepository,
            "buscar",
            side_effect=RuntimeError("caída al leer el presupuesto"),
        ),
        pytest.raises(RuntimeError),
    ):
        servicio.conciliar(escenario.comando)

    sesion_sin_transaccion_externa.rollback()

    comercios = list(sesion_sin_transaccion_externa.scalars(select(Comercio)))
    assert len(comercios) == 1
    assert comercios[0].nombre_normalizado == "WALMART SAN SEBASTIAN"
    assert _contar(sesion_sin_transaccion_externa, Compra) == 0, "pero la compra sí se revirtió"


def test_un_fallo_al_escribir_el_renglon_no_deja_la_compra_suelta(
    sesion_sin_transaccion_externa: Session, escenario: _Escenario
) -> None:
    """`flush` no es `commit`.

    `CompraRepository.agregar` hace `flush` para que la compra reciba su id y
    `LineaCompra` pueda apuntarle. Esta prueba fija que ese `flush` sigue
    dentro de la transacción: si el renglón falla justo después, la compra que
    ya tenía id tampoco queda. Una compra sin ningún renglón no tiene
    categoría ni gasto asociado -no aparecería en ningún reporte, pero sí en
    la lista del titular.
    """
    servicio = _armar(sesion_sin_transaccion_externa)

    with (
        patch.object(
            LineaCompraRepository,
            "agregar",
            side_effect=RuntimeError("caída al escribir el renglón"),
        ),
        pytest.raises(RuntimeError),
    ):
        servicio.conciliar(escenario.comando)

    sesion_sin_transaccion_externa.rollback()

    assert _contar(sesion_sin_transaccion_externa, Compra) == 0
    assert _contar(sesion_sin_transaccion_externa, LineaCompra) == 0
    comprobante = sesion_sin_transaccion_externa.scalars(
        select(Comprobante).where(Comprobante.id == escenario.comprobante.id)
    ).one()
    assert comprobante.compra_id is None


def test_una_conciliacion_completa_si_escribe_las_cinco_tablas(
    sesion_sin_transaccion_externa: Session, escenario: _Escenario
) -> None:
    """El contraste que le da sentido a las tres de arriba.

    Sin provocar ningún fallo, la misma llamada escribe en las cinco tablas y
    confirma. Si esta prueba fallara, las otras tres pasarían por el motivo
    equivocado -verificar que "no quedó nada" es trivial si el servicio nunca
    escribe nada.
    """
    servicio = _armar(sesion_sin_transaccion_externa)

    resultado = servicio.conciliar(escenario.comando)

    assert resultado.compra_id is not None
    assert resultado.requiere_revision is False

    compra = sesion_sin_transaccion_externa.scalars(select(Compra)).one()
    assert compra.total == MONTO
    assert compra.fecha == date(2026, 8, 30)
    assert compra.metodo_pago_id == escenario.metodo_pago.id

    linea = sesion_sin_transaccion_externa.scalars(select(LineaCompra)).one()
    assert linea.compra_id == compra.id
    assert linea.categoria_id == escenario.categoria.id

    sesion_sin_transaccion_externa.refresh(escenario.presupuesto)
    sesion_sin_transaccion_externa.refresh(escenario.regla)
    sesion_sin_transaccion_externa.refresh(escenario.comprobante)
    assert escenario.presupuesto.monto_consumido == MONTO
    assert escenario.regla.veces_aplicada == 1
    assert escenario.comprobante.compra_id == compra.id
    assert escenario.comprobante.estado == EstadoComprobante.PROCESADO
