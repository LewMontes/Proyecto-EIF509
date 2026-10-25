"""El bloqueo optimista contra PostgreSQL real, con la columna `version` de V9.

`tests/test_concurrencia_presupuesto.py` provoca la carrera sobre SQLite. Acá
se repite donde importa: dos conexiones de verdad a PostgreSQL, cada una con su
transacción en `READ COMMITTED` -el nivel por defecto-, sobre el esquema que
crean las migraciones de Flyway y no el mapeo.

Estas pruebas no pueden usar la transacción externa que se revierte de
`sesion_postgres`: para que haya dos transacciones que choquen, cada una tiene
que confirmar de verdad. Por eso crean sus datos con un correo propio y los
borran al terminar.
"""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.business.seguridad.contrasenas import hashear_contrasena
from app.data.models.categoria import Categoria
from app.data.models.enums import Moneda
from app.data.models.presupuesto import Presupuesto
from app.data.models.usuario import Usuario
from tests.conftest import COSTO_DE_HASH_EN_PRUEBAS

pytestmark = pytest.mark.integracion

CORREO = "concurrencia@gastonomo.cr"


@pytest.fixture
def presupuesto_confirmado(motor_postgres: Engine) -> Iterator[int]:
    """Un presupuesto confirmado de verdad, que se borra al terminar la prueba."""
    with Session(motor_postgres) as sesion:
        usuario = Usuario(
            nombre_completo="Prueba de concurrencia",
            correo=CORREO,
            contrasena_hash=hashear_contrasena("una-clave-larga", COSTO_DE_HASH_EN_PRUEBAS),
        )
        sesion.add(usuario)
        sesion.flush()
        categoria = Categoria(
            usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E", es_hoja=True
        )
        sesion.add(categoria)
        sesion.flush()
        presupuesto = Presupuesto(
            usuario_id=usuario.id,
            categoria_id=categoria.id,
            anio=2026,
            mes=10,
            moneda=Moneda.CRC,
            monto_limite=Decimal("100000.00"),
            monto_consumido=Decimal("0"),
        )
        sesion.add(presupuesto)
        sesion.commit()
        usuario_id, presupuesto_id = usuario.id, presupuesto.id

    yield presupuesto_id

    with Session(motor_postgres) as sesion:
        sesion.execute(delete(Presupuesto).where(Presupuesto.usuario_id == usuario_id))
        sesion.execute(delete(Categoria).where(Categoria.usuario_id == usuario_id))
        sesion.execute(delete(Usuario).where(Usuario.id == usuario_id))
        sesion.commit()


def test_la_migracion_v9_deja_la_columna_version_en_1(
    motor_postgres: Engine, presupuesto_confirmado: int
) -> None:
    with motor_postgres.connect() as conexion:
        version = conexion.execute(
            text("SELECT version FROM presupuesto WHERE id = :id"), {"id": presupuesto_confirmado}
        ).scalar_one()

    assert version == 1


def test_en_postgres_la_segunda_escritura_concurrente_es_rechazada(
    motor_postgres: Engine, presupuesto_confirmado: int
) -> None:
    fabrica = sessionmaker(bind=motor_postgres, expire_on_commit=False)
    with fabrica() as conciliacion, fabrica() as registro_manual:
        en_conciliacion = conciliacion.get(Presupuesto, presupuesto_confirmado)
        en_registro = registro_manual.get(Presupuesto, presupuesto_confirmado)

        en_registro.monto_consumido += Decimal("30000.00")
        registro_manual.commit()

        en_conciliacion.monto_consumido += Decimal("12500.00")
        with pytest.raises(StaleDataError):
            conciliacion.commit()
        conciliacion.rollback()

    with Session(motor_postgres) as sesion:
        final = sesion.get(Presupuesto, presupuesto_confirmado)
        assert final.monto_consumido == Decimal("30000.00")
        assert final.version == 2
