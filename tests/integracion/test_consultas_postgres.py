"""Las consultas de negocio, contra el PostgreSQL real que van a usar.

La consulta agregada y la corrección del N+1 están probadas en `tests/` contra
SQLite, y ahí verifican que el **resultado** sea el correcto. Lo que no pueden
verificar es que el SQL que SQLAlchemy genera para PostgreSQL diga lo mismo:
`extract()`, la aritmética de `NUMERIC`, el `LEFT OUTER JOIN` que produce
`joinedload` sobre una relación opcional y el `WHERE ... IN (...)` de
`selectinload` son cosas que cada motor resuelve a su manera.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.business.services.compra_service import CompraService
from app.data.models.categoria import Categoria
from app.data.models.comercio import Comercio
from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra, Moneda, TipoMetodoPago
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.models.usuario import Usuario
from app.data.repositories.compra_repository import CompraRepository

pytestmark = pytest.mark.integracion


@pytest.fixture
def titular(sesion_postgres: Session) -> Usuario:
    usuario = Usuario(
        nombre_completo="Titular de prueba",
        correo="consultas@gastonomo.cr",
        contrasena_hash="hash-de-prueba",
        moneda_preferida=Moneda.CRC,
    )
    sesion_postgres.add(usuario)
    sesion_postgres.flush()
    return usuario


@pytest.fixture
def servicio(sesion_postgres: Session) -> CompraService:
    return CompraService(CompraRepository(sesion_postgres))


def _compra(
    sesion: Session,
    usuario: Usuario,
    fecha: date,
    monto: str,
    categoria: Categoria | None = None,
    metodo_pago: MetodoPago | None = None,
    moneda: Moneda = Moneda.CRC,
    tipo_cambio: str = "1",
    estado: EstadoCompra = EstadoCompra.CONCILIADA,
    sufijo: str = "",
) -> Compra:
    comercio = Comercio(nombre=f"Comercio{sufijo}", nombre_normalizado=f"comercio{sufijo}".lower())
    sesion.add(comercio)
    sesion.flush()
    compra = Compra(
        usuario_id=usuario.id,
        comercio_id=comercio.id,
        metodo_pago_id=metodo_pago.id if metodo_pago else None,
        fecha=fecha,
        moneda=moneda,
        estado=estado,
        tipo_cambio_aplicado=Decimal(tipo_cambio),
        total=Decimal(monto),
        total_moneda_base=Decimal(monto) * Decimal(tipo_cambio),
    )
    sesion.add(compra)
    sesion.flush()
    sesion.add(
        LineaCompra(
            compra_id=compra.id,
            categoria_id=categoria.id if categoria else None,
            descripcion="Renglon",
            cantidad=1,
            precio_unitario=Decimal(monto),
            subtotal=Decimal(monto),
        )
    )
    sesion.flush()
    return compra


def test_el_gasto_por_categoria_suma_igual_en_postgres(
    sesion_postgres: Session, titular: Usuario, servicio: CompraService
) -> None:
    """`extract('month', ...)`, `SUM` sobre `NUMERIC` y `GROUP BY`, de verdad.

    La conversión de moneda es la parte delicada: 20 dólares a 512.37 son
    10247.40 colones exactos. En SQLite esa multiplicación pasa por punto
    flotante y el resultado se redondea "casi bien"; acá lo hace la aritmética
    decimal de PostgreSQL y tiene que dar el céntimo justo.
    """
    alimentacion = Categoria(
        usuario_id=titular.id, nombre="Alimentacion", color_hex="#16A34A", es_hoja=True
    )
    suscripciones = Categoria(
        usuario_id=titular.id, nombre="Suscripciones", color_hex="#9333EA", es_hoja=True
    )
    sesion_postgres.add_all([alimentacion, suscripciones])
    sesion_postgres.flush()

    _compra(sesion_postgres, titular, date(2026, 9, 3), "12500", alimentacion, sufijo="1")
    _compra(sesion_postgres, titular, date(2026, 9, 20), "3500", alimentacion, sufijo="2")
    _compra(
        sesion_postgres,
        titular,
        date(2026, 9, 10),
        "20",
        suscripciones,
        moneda=Moneda.USD,
        tipo_cambio="512.37",
        sufijo="3",
    )
    # Fuera del mes, y una anulada: ninguna debe contar.
    _compra(sesion_postgres, titular, date(2026, 8, 31), "90000", alimentacion, sufijo="4")
    _compra(
        sesion_postgres,
        titular,
        date(2026, 9, 15),
        "77000",
        alimentacion,
        estado=EstadoCompra.ANULADA,
        sufijo="5",
    )

    filas = servicio.gasto_por_categoria_del_titular(titular.id, 2026, 9)

    assert [(f.categoria_nombre, f.total) for f in filas] == [
        ("Alimentacion", Decimal("16000.00")),
        ("Suscripciones", Decimal("10247.40")),
    ]


def test_el_n_mas_1_sigue_corregido_contra_postgres(
    sesion_postgres: Session, titular: Usuario, servicio: CompraService
) -> None:
    """Listar 40 compras cuesta 2 consultas también acá.

    Contra SQLite ya está probado en `tests/test_n_mas_1.py`. Lo que agrega
    esta: que el `LEFT OUTER JOIN` de `joinedload` y el `WHERE compra_id IN
    (...)` de `selectinload` son válidos y siguen siendo dos viajes contra un
    motor real, no una particularidad del dialecto de SQLite.
    """
    categoria = Categoria(
        usuario_id=titular.id, nombre="Supermercado", color_hex="#22C55E", es_hoja=True
    )
    metodo = MetodoPago(
        usuario_id=titular.id,
        alias="Visa BAC",
        tipo=TipoMetodoPago.CREDITO,
        ultimos_cuatro="1234",
    )
    sesion_postgres.add_all([categoria, metodo])
    sesion_postgres.flush()
    for indice in range(40):
        _compra(
            sesion_postgres,
            titular,
            date(2026, 9, 1),
            "1000",
            categoria,
            metodo,
            sufijo=str(indice),
        )
    sesion_postgres.expunge_all()

    consultas: list[str] = []

    def registrar(_conn, _cursor, sentencia, *_resto):
        if sentencia.lstrip().upper().startswith("SELECT"):
            consultas.append(sentencia)

    motor = sesion_postgres.get_bind()
    event.listen(motor, "before_cursor_execute", registrar)
    try:
        detalladas = servicio.listar_del_titular(titular.id, limite=40)
    finally:
        event.remove(motor, "before_cursor_execute", registrar)

    assert len(detalladas) == 40
    assert len(consultas) == 2, "\n".join(consultas)
    # La primera consulta es la que trae las compras: tiene que llevar los
    # LEFT JOIN de joinedload, no INNER JOIN -si no, las compras sin método
    # de pago desaparecerían.
    assert "LEFT OUTER JOIN" in consultas[0].upper()


def test_la_lista_conserva_las_compras_sin_metodo_de_pago(
    sesion_postgres: Session, titular: Usuario, servicio: CompraService
) -> None:
    """Justo las que hay que revisar son las que un `JOIN` interno escondería."""
    _compra(sesion_postgres, titular, date(2026, 9, 1), "5000", sufijo="a")

    detalladas = servicio.listar_del_titular(titular.id)

    assert len(detalladas) == 1
    assert detalladas[0].metodo_pago_alias is None
    assert detalladas[0].categoria_nombre is None
    assert detalladas[0].comercio_nombre == "Comercioa"
