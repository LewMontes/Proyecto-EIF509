"""Bloqueo optimista del presupuesto: dos escrituras sobre el mismo dato.

El escenario que lo justifica: el comprobante de una compra llega por correo y
se concilia (Proceso 2) en el mismo momento en que el titular registra a mano
otra compra de la misma categoría (Proceso 1). Las dos transacciones leen el
mismo `monto_consumido`, le suman su monto y escriben. Sin control, la segunda
pisa a la primera y un gasto desaparece del presupuesto.

Estas pruebas provocan esa carrera de verdad -dos sesiones, dos transacciones,
sobre la misma fila- y verifican las tres cosas que pide el laboratorio: que la
segunda escritura se rechaza, que no se pierde nada, y que la API responde
`409` con Problem Details.
"""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.business.errors import ConflictoDeConcurrencia
from app.business.services.presupuesto_service import PresupuestoService
from app.data.models import Base, Usuario
from app.data.models.categoria import Categoria
from app.data.models.enums import Moneda
from app.data.models.presupuesto import Presupuesto
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.usuario_repository import UsuarioRepository
from app.presentation.dependencies import obtener_servicio_de_presupuestos

# ---- la carrera, con dos sesiones de verdad ----


@pytest.fixture
def motor(tmp_path: Path) -> Iterator[Engine]:
    """Una base SQLite en archivo, para que cada sesión tenga su propia conexión.

    La de `conftest.py` es en memoria con `StaticPool`: todas las sesiones
    comparten una sola conexión, y ahí no hay dos transacciones que puedan
    chocar.
    """
    motor = create_engine(f"sqlite:///{tmp_path / 'concurrencia.sqlite3'}")
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def presupuesto_id(motor: Engine) -> int:
    """Un presupuesto de 100 000 colones, sin consumo, ya confirmado."""
    with Session(motor) as sesion:
        usuario = Usuario(nombre_completo="Ana Mora", correo="ana@gastonomo.cr")
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
        return presupuesto.id


def test_un_presupuesto_nuevo_arranca_en_la_version_1(motor: Engine, presupuesto_id: int) -> None:
    with Session(motor) as sesion:
        assert sesion.get(Presupuesto, presupuesto_id).version == 1


def test_cada_cambio_confirmado_sube_la_version(motor: Engine, presupuesto_id: int) -> None:
    with Session(motor) as sesion:
        presupuesto = sesion.get(Presupuesto, presupuesto_id)
        presupuesto.monto_consumido += Decimal("5000")
        sesion.commit()
        presupuesto.monto_limite = Decimal("120000")
        sesion.commit()

        assert presupuesto.version == 3


def test_dos_compras_simultaneas_la_segunda_en_confirmar_choca(
    motor: Engine, presupuesto_id: int
) -> None:
    """La carrera del Proceso 1 contra el Proceso 2, paso a paso."""
    fabrica = sessionmaker(bind=motor, expire_on_commit=False)
    with fabrica() as conciliacion, fabrica() as registro_manual:
        # Las dos transacciones leen el mismo presupuesto: consumido 0, versión 1.
        en_conciliacion = conciliacion.get(Presupuesto, presupuesto_id)
        en_registro = registro_manual.get(Presupuesto, presupuesto_id)
        assert en_conciliacion.version == en_registro.version == 1

        # El registro manual confirma primero su compra de 30 000.
        en_registro.monto_consumido += Decimal("30000")
        registro_manual.commit()

        # La conciliación todavía cree que el consumido es 0 y que la versión
        # es 1. Su UPDATE ... WHERE version = 1 no encuentra la fila.
        en_conciliacion.monto_consumido += Decimal("12500")
        with pytest.raises(StaleDataError):
            conciliacion.commit()
        conciliacion.rollback()

    with Session(motor) as sesion:
        final = sesion.get(Presupuesto, presupuesto_id)
        # Quedó la compra que llegó primero, entera, y no un 12 500 que la pisó.
        assert final.monto_consumido == Decimal("30000")
        assert final.version == 2


def test_quien_choca_reintenta_sobre_lo_actual_y_no_se_pierde_ningun_gasto(
    motor: Engine, presupuesto_id: int
) -> None:
    """La salida del conflicto: volver a leer y aplicar el cambio sobre el dato vigente."""
    fabrica = sessionmaker(bind=motor, expire_on_commit=False)
    with fabrica() as primera, fabrica() as segunda:
        a = primera.get(Presupuesto, presupuesto_id)
        b = segunda.get(Presupuesto, presupuesto_id)
        b.monto_consumido += Decimal("30000")
        segunda.commit()
        a.monto_consumido += Decimal("12500")
        with pytest.raises(StaleDataError):
            primera.commit()
        primera.rollback()

        # Reintento: la sesión vuelve a leer la fila y suma sobre lo vigente.
        a = primera.get(Presupuesto, presupuesto_id, populate_existing=True)
        a.monto_consumido += Decimal("12500")
        primera.commit()

    with Session(motor) as sesion:
        final = sesion.get(Presupuesto, presupuesto_id)
        assert final.monto_consumido == Decimal("42500"), "las dos compras, ninguna perdida"
        assert final.version == 3


# ---- el servicio: una versión vieja se rechaza antes de escribir ----


def _servicio(sesion: Session) -> PresupuestoService:
    return PresupuestoService(
        PresupuestoRepository(sesion), CategoriaRepository(sesion), UsuarioRepository(sesion)
    )


def test_el_servicio_rechaza_corregir_con_una_version_vieja(
    motor: Engine, presupuesto_id: int
) -> None:
    with Session(motor, expire_on_commit=False) as sesion:
        usuario_id = sesion.get(Presupuesto, presupuesto_id).usuario_id
        servicio = _servicio(sesion)
        servicio.actualizar(usuario_id, presupuesto_id, Decimal("150000"), 80, version_esperada=1)

        with pytest.raises(ConflictoDeConcurrencia):
            servicio.actualizar(
                usuario_id, presupuesto_id, Decimal("90000"), 80, version_esperada=1
            )

        assert sesion.get(Presupuesto, presupuesto_id).monto_limite == Decimal("150000")


# ---- la API: el conflicto llega al cliente como 409 con Problem Details ----


def _crear_presupuesto(cliente: TestClient) -> dict:
    categoria = cliente.post(
        "/api/v1/categorias", json={"nombre": "Supermercado", "color_hex": "#22C55E"}
    ).json()
    respuesta = cliente.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria["id"],
            "anio": 2026,
            "mes": 10,
            "moneda": "CRC",
            "monto_limite": "100000.00",
        },
    )
    assert respuesta.status_code == 201
    return respuesta.json()


def test_la_respuesta_trae_la_version_y_el_put_la_sube(cliente: TestClient) -> None:
    creado = _crear_presupuesto(cliente)
    assert creado["version"] == 1

    respuesta = cliente.put(
        f"/api/v1/presupuestos/{creado['id']}",
        json={"monto_limite": "120000.00", "umbral_alerta": 80, "version": 1},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["version"] == 2


def test_dos_titulares_editan_a_la_vez_el_segundo_recibe_409(cliente: TestClient) -> None:
    """Dos pestañas abiertas sobre el mismo presupuesto, las dos con la versión 1."""
    creado = _crear_presupuesto(cliente)
    ruta = f"/api/v1/presupuestos/{creado['id']}"

    primera = cliente.put(
        ruta, json={"monto_limite": "150000.00", "umbral_alerta": 80, "version": 1}
    )
    segunda = cliente.put(
        ruta, json={"monto_limite": "90000.00", "umbral_alerta": 70, "version": 1}
    )

    assert primera.status_code == 200
    assert segunda.status_code == 409
    assert segunda.headers["content-type"] == "application/problem+json"
    problema = segunda.json()
    assert problema["status"] == 409
    assert problema["codigo"] == "ConflictoDeConcurrencia"
    assert problema["type"].endswith("#conflicto-de-concurrencia")
    assert problema["instance"] == ruta
    # Lo que quedó es lo de la primera, intacto.
    vigente = cliente.get(ruta).json()
    assert float(vigente["monto_limite"]) == 150000
    assert vigente["version"] == 2


def test_un_put_sin_version_sigue_funcionando(cliente: TestClient) -> None:
    """El campo es opcional: los clientes de antes del Laboratorio 7 no se rompen."""
    creado = _crear_presupuesto(cliente)

    respuesta = cliente.put(
        f"/api/v1/presupuestos/{creado['id']}",
        json={"monto_limite": "120000.00", "umbral_alerta": 80},
    )

    assert respuesta.status_code == 200


class _ServicioQueChocaAlConfirmar:
    """Un servicio cuyo `commit` pierde la carrera: lo que pasa cuando el UPDATE
    con versión no encuentra la fila entre la lectura y la escritura."""

    def actualizar(self, *args, **kwargs):
        raise StaleDataError("UPDATE statement on table 'presupuesto' expected to update 1 row")


def test_el_stale_data_error_se_traduce_a_409_en_el_manejador_global(
    cliente: TestClient, aplicacion
) -> None:
    aplicacion.dependency_overrides[obtener_servicio_de_presupuestos] = lambda: (
        _ServicioQueChocaAlConfirmar()
    )

    respuesta = cliente.put(
        "/api/v1/presupuestos/1", json={"monto_limite": "1000.00", "umbral_alerta": 80}
    )

    assert respuesta.status_code == 409
    assert respuesta.headers["content-type"] == "application/problem+json"
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "ConflictoDeConcurrencia"
    assert "presupuesto" not in cuerpo["detail"], "el mensaje del ORM no llega al cliente"
