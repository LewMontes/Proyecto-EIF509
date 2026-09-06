"""Lo que solo PostgreSQL puede decir sobre el esquema y los tipos.

Cada prueba de este archivo verifica algo que la suite sobre SQLite **no
puede** detectar. Ese es el criterio para que una prueba viva acá y no en
`tests/`: si SQLite la puede probar igual de bien, no justifica levantar un
contenedor.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.data.models import Base
from app.data.models.categoria import Categoria
from app.data.models.compra import Compra
from app.data.models.cuenta_correo import CuentaCorreo
from app.data.models.enums import EstadoCuentaCorreo, Moneda, ProveedorCorreo
from app.data.models.linea_compra import LineaCompra
from app.data.models.usuario import Usuario

pytestmark = pytest.mark.integracion


def _titular(sesion: Session, correo: str = "titular@gastonomo.cr") -> Usuario:
    usuario = Usuario(
        nombre_completo="Titular de prueba",
        correo=correo,
        contrasena_hash="hash-de-prueba",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(usuario)
    sesion.flush()
    return usuario


def _comercio_y_compra(sesion: Session, usuario: Usuario, total: str = "10000") -> Compra:
    from app.data.models.comercio import Comercio

    comercio = Comercio(nombre="Automercado", nombre_normalizado="automercado")
    sesion.add(comercio)
    sesion.flush()
    compra = Compra(
        usuario_id=usuario.id,
        comercio_id=comercio.id,
        fecha=date(2026, 9, 1),
        moneda=Moneda.CRC,
        total=Decimal(total),
        total_moneda_base=Decimal(total),
    )
    sesion.add(compra)
    sesion.flush()
    return compra


def test_borrar_una_compra_arrastra_sus_renglones(sesion_postgres: Session) -> None:
    """El `ON DELETE CASCADE` de verdad, aplicado por la base.

    SQLite no lo aplica salvo que se encienda `PRAGMA foreign_keys`, y la
    fixture de `tests/conftest.py` no lo enciende: ahí los renglones quedarían
    huérfanos y ninguna prueba se daría cuenta.

    Importa además porque `Compra.lineas` está mapeada con `passive_deletes`:
    SQLAlchemy delega el borrado en la base a propósito, en vez de cargar los
    renglones para borrarlos uno por uno. Si el CASCADE no existiera, ese
    borrado fallaría contra la llave foránea.
    """
    usuario = _titular(sesion_postgres)
    compra = _comercio_y_compra(sesion_postgres, usuario)
    sesion_postgres.add(
        LineaCompra(
            compra_id=compra.id,
            descripcion="Renglon",
            cantidad=1,
            precio_unitario=Decimal("10000"),
            subtotal=Decimal("10000"),
        )
    )
    sesion_postgres.flush()
    compra_id = compra.id
    assert sesion_postgres.scalar(select(LineaCompra).where(LineaCompra.compra_id == compra_id))

    sesion_postgres.delete(compra)
    sesion_postgres.flush()

    quedan = sesion_postgres.scalars(
        select(LineaCompra).where(LineaCompra.compra_id == compra_id)
    ).all()
    assert quedan == []


def test_numeric_conserva_los_centimos_sin_error_de_punto_flotante(
    sesion_postgres: Session,
) -> None:
    """`NUMERIC(14,2)` es decimal exacto en PostgreSQL; en SQLite es un float.

    El caso es el de una conversión de moneda: 19.99 dólares a 512.37 son
    10242.28 colones. Con punto flotante el resultado arrastra un error que
    aparece recién cuando se suman cientos de compras y el total del mes no
    cuadra contra el consumo del presupuesto.
    """
    usuario = _titular(sesion_postgres)
    compra = _comercio_y_compra(sesion_postgres, usuario)
    compra.moneda = Moneda.USD
    compra.total = Decimal("19.99")
    compra.tipo_cambio_aplicado = Decimal("512.37")
    compra.total_moneda_base = Decimal("10242.28")
    sesion_postgres.flush()
    sesion_postgres.expunge_all()

    recuperada = sesion_postgres.get(Compra, compra.id)
    assert isinstance(recuperada.total_moneda_base, Decimal)
    assert recuperada.total_moneda_base == Decimal("10242.28")
    assert recuperada.tipo_cambio_aplicado == Decimal("512.3700")
    # La suma la hace la base, con su propia aritmética decimal.
    suma = sesion_postgres.scalar(
        text("SELECT SUM(total_moneda_base) FROM compra WHERE usuario_id = :u"),
        {"u": usuario.id},
    )
    assert suma == Decimal("10242.28")


def test_una_cadena_mas_larga_que_su_columna_es_rechazada(
    sesion_postgres: Session,
) -> None:
    """La regresión del commit `32deefc`, ahora cubierta por una prueba.

    Vincular Outlook guardaba un token de acceso más largo que la columna que
    lo recibía. SQLite lo aceptó sin chistar durante toda la suite; PostgreSQL
    respondió `StringDataRightTruncation` la primera vez que alguien lo probó
    de verdad. Esta prueba es la que hace que no vuelva a pasar en silencio.
    """
    usuario = _titular(sesion_postgres)
    cuenta = CuentaCorreo(
        usuario_id=usuario.id,
        proveedor=ProveedorCorreo.OUTLOOK,
        # `direccion` es VARCHAR(180): 200 caracteres no caben.
        direccion="a" * 200 + "@outlook.com",
        estado=EstadoCuentaCorreo.ACTIVA,
    )
    sesion_postgres.add(cuenta)

    with pytest.raises(DataError):
        sesion_postgres.flush()


def test_el_unique_por_titular_y_nombre_rechaza_la_categoria_duplicada(
    sesion_postgres: Session,
) -> None:
    """`uq_categoria_usuario_nombre`, aplicado por PostgreSQL.

    Dos categorías con el mismo nombre en la misma cuenta harían ambiguo todo
    reporte. La restricción es del esquema, no del servicio: si algún día un
    camino nuevo se saltara la validación de negocio, la base sigue diciendo
    que no.
    """
    usuario = _titular(sesion_postgres)
    for _ in range(2):
        sesion_postgres.add(
            Categoria(
                usuario_id=usuario.id,
                nombre="Alimentacion",
                color_hex="#16A34A",
                es_hoja=True,
            )
        )

    with pytest.raises(IntegrityError):
        sesion_postgres.flush()


def test_una_transaccion_fallida_no_deja_nada_a_medias(sesion_postgres: Session) -> None:
    """El `ROLLBACK` real de PostgreSQL sobre una escritura en varias tablas.

    Es la garantía de la que depende `ConciliacionService`, que escribe en
    cinco tablas dentro de una sola transacción: si el último paso falla, no
    puede quedar una `Compra` registrada sin sus renglones, ni un presupuesto
    consumido por una compra que no existe.
    """
    usuario = _titular(sesion_postgres)
    punto = sesion_postgres.begin_nested()

    compra = _comercio_y_compra(sesion_postgres, usuario)
    sesion_postgres.add(
        LineaCompra(
            compra_id=compra.id,
            descripcion="Renglon",
            cantidad=1,
            precio_unitario=Decimal("10000"),
            subtotal=Decimal("10000"),
        )
    )
    sesion_postgres.flush()
    compra_id = compra.id

    punto.rollback()

    assert sesion_postgres.get(Compra, compra_id) is None
    assert (
        sesion_postgres.scalars(select(LineaCompra).where(LineaCompra.compra_id == compra_id)).all()
        == []
    )


def test_el_mapeo_calza_con_el_esquema_que_hay_en_la_base(
    sesion_postgres: Session,
) -> None:
    """El equivalente del `ddl-auto=validate` de Hibernate.

    No basta con que la aplicación arranque: arranca igual contra una base a
    la que le falta una columna, y revienta recién cuando alguien consulta esa
    tabla. Esta prueba compara, tabla por tabla y columna por columna, lo que
    el mapeo declara contra lo que PostgreSQL de verdad tiene.

    Hoy pasa porque el esquema lo crea el propio mapeo (`create_all`). El día
    que las migraciones Flyway sean la única fuente del esquema -ver
    docs/persistencia.md, sección 7- esta misma prueba es la que va a avisar
    si el mapeo y las migraciones se separan.
    """
    inspector = inspect(sesion_postgres.get_bind())
    tablas_reales = set(inspector.get_table_names())

    faltantes = set(Base.metadata.tables) - tablas_reales
    assert not faltantes, f"El mapeo declara tablas que no existen en la base: {faltantes}"

    diferencias: list[str] = []
    for nombre, tabla in Base.metadata.tables.items():
        columnas_reales = {c["name"] for c in inspector.get_columns(nombre)}
        columnas_mapeadas = {c.name for c in tabla.columns}
        if columnas_mapeadas - columnas_reales:
            diferencias.append(
                f"{nombre}: el mapeo espera {sorted(columnas_mapeadas - columnas_reales)}, "
                "que no están en la base"
            )

    assert not diferencias, "\n".join(diferencias)


def test_las_llaves_foraneas_del_mapeo_existen_en_la_base(
    sesion_postgres: Session,
) -> None:
    """Las veinte relaciones tienen su llave foránea de verdad detrás.

    Una relación mapeada sin su `FOREIGN KEY` en la base "funciona" -SQLAlchemy
    hace el `JOIN` igual- pero deja de garantizar la integridad referencial:
    nada impediría una compra apuntando a un comercio que ya no existe.
    """
    inspector = inspect(sesion_postgres.get_bind())
    total_reales = 0
    for nombre in Base.metadata.tables:
        total_reales += len(inspector.get_foreign_keys(nombre))

    total_mapeadas = sum(len(tabla.foreign_keys) for tabla in Base.metadata.tables.values())
    assert total_reales == total_mapeadas == 20
