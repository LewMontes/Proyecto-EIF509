"""La consulta agregada: gasto del mes por categoría.

Lo que se verifica acá no es "devuelve filas", sino las cuatro decisiones que
hacen que el número signifique algo: que suma renglones y no compras, que
normaliza la moneda con la tasa congelada de cada compra, que deja fuera lo
anulado, y que los filtros opcionales se combinan sin pisarse.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.business.errors import ValidacionFallida
from app.business.services.compra_service import CompraService
from app.data.models.categoria import Categoria
from app.data.models.comercio import Comercio
from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra, Moneda, TipoMetodoPago
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.models.usuario import Usuario
from app.data.repositories.compra_repository import CompraRepository


@pytest.fixture
def servicio(sesion: Session) -> CompraService:
    return CompraService(CompraRepository(sesion))


def _categoria(sesion: Session, usuario: Usuario, nombre: str) -> Categoria:
    categoria = Categoria(usuario_id=usuario.id, nombre=nombre, color_hex="#22C55E", es_hoja=True)
    sesion.add(categoria)
    sesion.flush()
    return categoria


def _comercio(sesion: Session, nombre: str) -> Comercio:
    comercio = Comercio(nombre=nombre, nombre_normalizado=nombre.lower())
    sesion.add(comercio)
    sesion.flush()
    return comercio


def _compra_con_renglones(
    sesion: Session,
    usuario: Usuario,
    comercio: Comercio,
    fecha: date,
    renglones: list[tuple[Categoria | None, str]],
    moneda: Moneda = Moneda.CRC,
    tipo_cambio: str = "1",
    metodo_pago: MetodoPago | None = None,
    estado: EstadoCompra = EstadoCompra.CONCILIADA,
) -> Compra:
    """Una compra con los renglones indicados: `(categoría, subtotal)` cada uno."""
    compra = Compra(
        usuario_id=usuario.id,
        comercio_id=comercio.id,
        metodo_pago_id=metodo_pago.id if metodo_pago else None,
        fecha=fecha,
        moneda=moneda,
        estado=estado,
        tipo_cambio_aplicado=Decimal(tipo_cambio),
        total=sum(Decimal(monto) for _, monto in renglones),
        total_moneda_base=sum(Decimal(monto) * Decimal(tipo_cambio) for _, monto in renglones),
    )
    sesion.add(compra)
    sesion.flush()
    for categoria, monto in renglones:
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


def test_agrupa_y_suma_por_categoria_de_mayor_a_menor(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    alimentacion = _categoria(sesion, usuario, "Alimentacion")
    transporte = _categoria(sesion, usuario, "Transporte")
    tienda = _comercio(sesion, "Tienda")

    _compra_con_renglones(sesion, usuario, tienda, date(2026, 9, 3), [(alimentacion, "10000")])
    _compra_con_renglones(sesion, usuario, tienda, date(2026, 9, 10), [(alimentacion, "5000")])
    _compra_con_renglones(sesion, usuario, tienda, date(2026, 9, 15), [(transporte, "8000")])
    sesion.commit()

    filas = servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9)

    assert [(f.categoria_nombre, f.total) for f in filas] == [
        ("Alimentacion", Decimal("15000.00")),
        ("Transporte", Decimal("8000.00")),
    ]
    assert filas[0].cantidad_de_renglones == 2


def test_una_compra_con_dos_categorias_no_se_cuenta_dos_veces(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    """El motivo de sumar renglones y no `Compra.total`.

    Una compra de 12000 desglosada en 9000 de super y 3000 de farmacia tiene
    que aportar 9000 a una y 3000 a la otra -no 12000 a cada una, que es lo
    que daría agrupar el total de la compra por categoría.
    """
    supermercado = _categoria(sesion, usuario, "Supermercado")
    farmacia = _categoria(sesion, usuario, "Farmacia")
    tienda = _comercio(sesion, "Automercado")

    _compra_con_renglones(
        sesion,
        usuario,
        tienda,
        date(2026, 9, 4),
        [(supermercado, "9000"), (farmacia, "3000")],
    )
    sesion.commit()

    filas = servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9)

    assert {f.categoria_nombre: f.total for f in filas} == {
        "Supermercado": Decimal("9000.00"),
        "Farmacia": Decimal("3000.00"),
    }
    assert sum(f.total for f in filas) == Decimal("12000.00")


def test_convierte_a_moneda_base_con_la_tasa_de_cada_compra(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    """Dos compras de la misma categoría en monedas distintas suman en base.

    20 dólares a 520 son 10400 colones; sumados a 5000 colones dan 15400. Sin
    multiplicar por `tipo_cambio_aplicado`, el resultado sería 5020: un número
    que no significa nada.
    """
    suscripciones = _categoria(sesion, usuario, "Suscripciones")
    netflix = _comercio(sesion, "Netflix")
    soda = _comercio(sesion, "Soda")

    _compra_con_renglones(
        sesion,
        usuario,
        netflix,
        date(2026, 9, 5),
        [(suscripciones, "20")],
        moneda=Moneda.USD,
        tipo_cambio="520",
    )
    _compra_con_renglones(sesion, usuario, soda, date(2026, 9, 6), [(suscripciones, "5000")])
    sesion.commit()

    filas = servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9)

    assert filas[0].total == Decimal("15400.00")


def test_deja_fuera_las_compras_anuladas_y_los_otros_meses(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    hogar = _categoria(sesion, usuario, "Hogar")
    ferreteria = _comercio(sesion, "Ferreteria")

    _compra_con_renglones(sesion, usuario, ferreteria, date(2026, 9, 8), [(hogar, "7000")])
    _compra_con_renglones(
        sesion,
        usuario,
        ferreteria,
        date(2026, 9, 9),
        [(hogar, "99000")],
        estado=EstadoCompra.ANULADA,
    )
    _compra_con_renglones(sesion, usuario, ferreteria, date(2026, 8, 30), [(hogar, "50000")])
    sesion.commit()

    filas = servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9)

    assert [f.total for f in filas] == [Decimal("7000.00")]


def test_los_renglones_sin_categoria_salen_en_su_propia_fila(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    """Y se pueden excluir: es el filtro que separa "gasté" de "gasté y no sé en qué"."""
    salud = _categoria(sesion, usuario, "Salud")
    clinica = _comercio(sesion, "Clinica")

    _compra_con_renglones(sesion, usuario, clinica, date(2026, 9, 11), [(salud, "30000")])
    _compra_con_renglones(sesion, usuario, clinica, date(2026, 9, 12), [(None, "4000")])
    sesion.commit()

    con_todo = servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9)
    sin_clasificar = [f for f in con_todo if f.categoria_id is None]
    assert len(sin_clasificar) == 1
    assert sin_clasificar[0].categoria_nombre == "Sin categoria"
    assert sin_clasificar[0].total == Decimal("4000.00")

    solo_clasificado = servicio.gasto_por_categoria_del_titular(
        usuario.id, 2026, 9, incluir_sin_categoria=False
    )
    assert [f.categoria_nombre for f in solo_clasificado] == ["Salud"]


def test_los_filtros_opcionales_se_combinan(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    """La parte dinámica: cada filtro agrega su `WHERE` sin pisar a los otros."""
    alimentacion = _categoria(sesion, usuario, "Alimentacion")
    ropa = _categoria(sesion, usuario, "Ropa")
    tienda = _comercio(sesion, "Tienda")
    tarjeta = MetodoPago(
        usuario_id=usuario.id,
        alias="Visa BAC",
        tipo=TipoMetodoPago.CREDITO,
        ultimos_cuatro="1234",
    )
    efectivo = MetodoPago(usuario_id=usuario.id, alias="Efectivo", tipo=TipoMetodoPago.EFECTIVO)
    sesion.add_all([tarjeta, efectivo])
    sesion.flush()

    _compra_con_renglones(
        sesion, usuario, tienda, date(2026, 9, 2), [(alimentacion, "6000")], metodo_pago=tarjeta
    )
    _compra_con_renglones(
        sesion, usuario, tienda, date(2026, 9, 3), [(alimentacion, "2000")], metodo_pago=efectivo
    )
    _compra_con_renglones(
        sesion, usuario, tienda, date(2026, 9, 4), [(ropa, "25000")], metodo_pago=tarjeta
    )
    sesion.commit()

    solo_tarjeta = servicio.gasto_por_categoria_del_titular(
        usuario.id, 2026, 9, metodo_pago_id=tarjeta.id
    )
    assert {f.categoria_nombre: f.total for f in solo_tarjeta} == {
        "Ropa": Decimal("25000.00"),
        "Alimentacion": Decimal("6000.00"),
    }

    tarjeta_y_alimentacion = servicio.gasto_por_categoria_del_titular(
        usuario.id, 2026, 9, categoria_ids=[alimentacion.id], metodo_pago_id=tarjeta.id
    )
    assert [(f.categoria_nombre, f.total) for f in tarjeta_y_alimentacion] == [
        ("Alimentacion", Decimal("6000.00"))
    ]


def test_no_mezcla_el_gasto_de_otro_titular(
    sesion: Session, usuario: Usuario, servicio: CompraService
) -> None:
    """El aislamiento entre cuentas también en la consulta agregada.

    Es donde más fácil se cuela: un `GROUP BY` que olvide el filtro por
    titular devuelve un total que parece correcto y que suma el gasto de todo
    el mundo.
    """
    otro = Usuario(
        nombre_completo="Otro titular",
        correo="otro@gastonomo.cr",
        contrasena_hash="x",
        moneda_preferida=Moneda.CRC,
    )
    sesion.add(otro)
    sesion.flush()

    mia = _categoria(sesion, usuario, "Alimentacion")
    suya = _categoria(sesion, otro, "Alimentacion")
    tienda = _comercio(sesion, "Tienda")

    _compra_con_renglones(sesion, usuario, tienda, date(2026, 9, 1), [(mia, "1000")])
    _compra_con_renglones(sesion, otro, tienda, date(2026, 9, 1), [(suya, "999000")])
    sesion.commit()

    filas = servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9)

    assert [f.total for f in filas] == [Decimal("1000.00")]


def test_un_mes_invalido_es_un_error_de_negocio(usuario: Usuario, servicio: CompraService) -> None:
    with pytest.raises(ValidacionFallida):
        servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 13)


def test_una_lista_de_categorias_vacia_es_un_error_de_negocio(
    usuario: Usuario, servicio: CompraService
) -> None:
    with pytest.raises(ValidacionFallida):
        servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9, categoria_ids=[])


def test_un_mes_sin_gasto_da_una_lista_vacia(usuario: Usuario, servicio: CompraService) -> None:
    assert servicio.gasto_por_categoria_del_titular(usuario.id, 2026, 9) == []


def test_el_endpoint_responde_el_gasto_del_mes(
    cliente: TestClient, sesion: Session, usuario: Usuario
) -> None:
    """Y de paso fija el orden de las rutas.

    `/api/compras/gasto-por-categoria` tiene que declararse antes que
    `/api/compras/{compra_id}`; si se invirtieran, esta llamada entraría por
    el detalle y daría 422 al no poder leer "gasto-por-categoria" como un id.
    """
    alimentacion = _categoria(sesion, usuario, "Alimentacion")
    tienda = _comercio(sesion, "Tienda")
    _compra_con_renglones(sesion, usuario, tienda, date(2026, 9, 3), [(alimentacion, "12500")])
    sesion.commit()

    respuesta = cliente.get(
        "/api/compras/gasto-por-categoria",
        params={"usuario_id": usuario.id, "anio": 2026, "mes": 9},
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == [
        {
            "categoria_id": alimentacion.id,
            "categoria_nombre": "Alimentacion",
            "total": "12500.00",
            "cantidad_de_renglones": 1,
        }
    ]


def test_el_endpoint_rechaza_un_mes_fuera_de_rango(cliente: TestClient, usuario: Usuario) -> None:
    respuesta = cliente.get(
        "/api/compras/gasto-por-categoria",
        params={"usuario_id": usuario.id, "anio": 2026, "mes": 13},
    )

    assert respuesta.status_code == 422
