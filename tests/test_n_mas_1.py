"""El N+1 al listar compras: la evidencia, ejecutable.

Estas pruebas no verifican un resultado de negocio -eso ya lo hacen
`test_compras_api.py` y `test_conciliacion_service.py`- sino **cuántas
consultas** cuesta producirlo.

Existen porque un N+1 no rompe nada: la pantalla devuelve exactamente los
mismos datos con 1 consulta que con 201, solo que más lento cada vez que
crece el historial del titular. Sin una prueba que cuente, la corrección se
deshace sola la próxima vez que alguien agregue un campo al detalle y lo
resuelva con `obtener_por_id` dentro del bucle -que es justo como apareció la
primera vez.

La medición documentada en docs/persistencia.md (sección 5) sale de acá.
"""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.business.services.compra_service import CompraService
from app.data.models.categoria import Categoria
from app.data.models.comercio import Comercio
from app.data.models.compra import Compra
from app.data.models.enums import Moneda, TipoMetodoPago
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.models.usuario import Usuario
from app.data.repositories.compra_repository import CompraRepository


class ContadorDeConsultas:
    """Cuenta los `SELECT` que salen hacia la base durante un bloque.

    Se engancha al evento `before_cursor_execute` del motor -el punto por el
    que pasa toda sentencia justo antes de ejecutarse- así que cuenta lo que
    de verdad llega al driver, no lo que uno cree que la consulta hace.
    """

    def __init__(self) -> None:
        self.sentencias: list[str] = []

    @property
    def total(self) -> int:
        return len(self.sentencias)

    def registrar(self, _conn, _cursor, sentencia: str, *_resto) -> None:
        if sentencia.lstrip().upper().startswith("SELECT"):
            self.sentencias.append(" ".join(sentencia.split()))


@pytest.fixture
def contador(sesion: Session) -> Iterator[ContadorDeConsultas]:
    """Contador enganchado al motor de la sesión de la prueba, ya en cero."""
    espia = ContadorDeConsultas()
    motor = sesion.get_bind()
    event.listen(motor, "before_cursor_execute", espia.registrar)
    yield espia
    event.remove(motor, "before_cursor_execute", espia.registrar)


def _catalogo(sesion: Session, usuario: Usuario) -> tuple[Categoria, MetodoPago]:
    """La categoría y el método de pago del titular, creándolos si no están.

    Buscar antes de crear porque una prueba siembra dos veces sobre la misma
    base -y `categoria` tiene un `UNIQUE (usuario_id, nombre)`.
    """
    categoria = sesion.query(Categoria).filter_by(usuario_id=usuario.id).first()
    if categoria is None:
        categoria = Categoria(
            usuario_id=usuario.id, nombre="Supermercado", color_hex="#22C55E", es_hoja=True
        )
        sesion.add(categoria)
    metodo = sesion.query(MetodoPago).filter_by(usuario_id=usuario.id).first()
    if metodo is None:
        metodo = MetodoPago(
            usuario_id=usuario.id,
            alias="Visa BAC",
            tipo=TipoMetodoPago.CREDITO,
            ultimos_cuatro="1234",
        )
        sesion.add(metodo)
    sesion.flush()
    return categoria, metodo


def _sembrar_compras(sesion: Session, usuario: Usuario, cuantas: int, desde: int = 0) -> None:
    """`cuantas` compras del titular, cada una en un comercio distinto.

    Un comercio distinto por compra a propósito: si todas compartieran el
    mismo, el caché de identidad de la sesión resolvería el segundo
    `obtener_por_id` sin ir a la base y el N+1 se vería más chico de lo que es
    con datos reales, donde cada compra es de un lugar distinto.
    """
    categoria, metodo = _catalogo(sesion, usuario)

    for indice in range(desde, desde + cuantas):
        comercio = Comercio(nombre=f"Comercio {indice}", nombre_normalizado=f"comercio {indice}")
        sesion.add(comercio)
        sesion.flush()
        compra = Compra(
            usuario_id=usuario.id,
            comercio_id=comercio.id,
            metodo_pago_id=metodo.id,
            fecha=date(2026, 9, 1),
            moneda=Moneda.CRC,
            total=10000,
            total_moneda_base=10000,
        )
        sesion.add(compra)
        sesion.flush()
        sesion.add(
            LineaCompra(
                compra_id=compra.id,
                descripcion="Compra completa",
                cantidad=1,
                precio_unitario=10000,
                subtotal=10000,
                categoria_id=categoria.id,
            )
        )
    sesion.commit()
    # La sesión guarda en su caché de identidad todo lo que acaba de crear; sin
    # vaciarla, listar leería de memoria y no mediría ninguna consulta real.
    sesion.expunge_all()


def test_listar_compras_no_crece_en_consultas_con_el_historial(
    sesion: Session, usuario: Usuario, contador: ContadorDeConsultas
) -> None:
    """Listar 50 compras cuesta lo mismo que listar 5.

    Es la prueba de que el N+1 está corregido, y la que lo mantiene corregido:
    con la versión vieja de `_detallar` esto daba 21 contra 201.
    """
    _sembrar_compras(sesion, usuario, 50)
    servicio = CompraService(CompraRepository(sesion))

    contador.sentencias.clear()
    detalladas = servicio.listar_del_titular(usuario.id)

    assert len(detalladas) == 50
    # 2: la de las compras (con sus JOIN a comercio y método de pago) y la de
    # los renglones con su categoría, que `selectinload` trae con un solo
    # `WHERE compra_id IN (...)`.
    assert contador.total == 2, (
        f"Listar 50 compras costó {contador.total} consultas:\n"
        + "\n".join(f"  {s[:120]}" for s in contador.sentencias)
    )


def test_el_costo_de_listar_no_depende_de_cuantas_compras_haya(
    sesion: Session, usuario: Usuario, contador: ContadorDeConsultas
) -> None:
    """El mismo conteo con 5 compras que con 50: el costo dejó de ser `1 + 4N`."""
    _sembrar_compras(sesion, usuario, 5)
    servicio = CompraService(CompraRepository(sesion))

    contador.sentencias.clear()
    servicio.listar_del_titular(usuario.id)
    con_cinco = contador.total

    _sembrar_compras(sesion, usuario, 45, desde=5)
    contador.sentencias.clear()
    servicio.listar_del_titular(usuario.id)
    con_cincuenta = contador.total

    assert con_cinco == con_cincuenta == 2


def test_la_lista_trae_las_compras_sin_metodo_de_pago(sesion: Session, usuario: Usuario) -> None:
    """La carga ansiosa no puede esconder justo las compras que hay que revisar.

    `metodo_pago_id` es nulo cuando la conciliación no logró emparejar la
    tarjeta, y esas son exactamente las que el titular tiene que corregir. Con
    un `JOIN` interno en vez de `LEFT JOIN` desaparecerían de la lista -por eso
    `joinedload` sobre una relación opcional genera `LEFT OUTER JOIN`, y esta
    prueba es la que lo fija.
    """
    _sembrar_compras(sesion, usuario, 2)
    huerfana = Comercio(nombre="Sin emparejar", nombre_normalizado="sin emparejar")
    sesion.add(huerfana)
    sesion.flush()
    sesion.add(
        Compra(
            usuario_id=usuario.id,
            comercio_id=huerfana.id,
            metodo_pago_id=None,
            fecha=date(2026, 9, 2),
            moneda=Moneda.CRC,
            total=5000,
            total_moneda_base=5000,
            requiere_revision=True,
        )
    )
    sesion.commit()

    servicio = CompraService(CompraRepository(sesion))
    detalladas = servicio.listar_del_titular(usuario.id)

    assert len(detalladas) == 3
    sin_metodo = [d for d in detalladas if d.metodo_pago_alias is None]
    assert len(sin_metodo) == 1
    assert sin_metodo[0].comercio_nombre == "Sin emparejar"

    solo_revision = servicio.listar_del_titular(usuario.id, requiere_revision=True)
    assert [d.comercio_nombre for d in solo_revision] == ["Sin emparejar"]


def test_el_detalle_de_una_compra_tambien_viene_cargado(
    sesion: Session, usuario: Usuario, contador: ContadorDeConsultas
) -> None:
    """Pedir una compra por id trae sus nombres en la misma consulta."""
    _sembrar_compras(sesion, usuario, 1)
    servicio = CompraService(CompraRepository(sesion))
    compra_id = servicio.listar_del_titular(usuario.id)[0].compra.id
    sesion.expunge_all()

    contador.sentencias.clear()
    detalle = servicio.obtener_detalle_del_titular(usuario.id, compra_id)

    assert detalle.comercio_nombre == "Comercio 0"
    assert detalle.metodo_pago_alias == "Visa BAC"
    assert detalle.categoria_nombre == "Supermercado"
    assert contador.total == 2
