"""Colecciones: paginación con metadatos, orden por parámetro y filtros de negocio.

Tres niveles, de adentro hacia afuera:

1. Las **especificaciones** solas: que se compongan y que la vacía no filtre.
2. El **servicio**: que arranque siempre del titular y valide los rangos.
3. El **endpoint**: `GET /api/v1/compras` con sus parámetros y su sobre.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.business.errors import RangoInvalido
from app.business.services.compra_service import CompraService, FiltrosDeCompra
from app.data.models.categoria import Categoria
from app.data.models.comercio import Comercio
from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra, Moneda, OrigenCompra
from app.data.models.linea_compra import LineaCompra
from app.data.models.usuario import Usuario
from app.data.paginacion import Orden, Pagina, SolicitudDePagina
from app.data.repositories import especificaciones as esp
from app.data.repositories.compra_repository import CompraRepository

# ---- datos de prueba ----


@pytest.fixture
def super_y_farmacia(sesion: Session, usuario: Usuario) -> tuple[Categoria, Categoria]:
    categorias = (
        Categoria(usuario_id=usuario.id, nombre="Supermercado", color_hex="#16A34A"),
        Categoria(usuario_id=usuario.id, nombre="Farmacia", color_hex="#DC2626"),
    )
    sesion.add_all(categorias)
    sesion.commit()
    return categorias


@pytest.fixture
def comercios(sesion: Session) -> tuple[Comercio, Comercio]:
    resultado = (
        Comercio(nombre="Walmart", nombre_normalizado="WALMART"),
        Comercio(nombre="Fischel", nombre_normalizado="FISCHEL"),
    )
    sesion.add_all(resultado)
    sesion.commit()
    return resultado


def _compra(
    sesion: Session,
    usuario: Usuario,
    comercio: Comercio,
    categoria: Categoria | None,
    fecha: date,
    total: str,
    **cambios,
) -> Compra:
    datos = dict(
        usuario_id=usuario.id,
        comercio_id=comercio.id,
        fecha=fecha,
        moneda=Moneda.CRC,
        estado=EstadoCompra.REGISTRADA,
        total=Decimal(total),
        total_moneda_base=Decimal(total),
    )
    compra = Compra(**{**datos, **cambios})
    sesion.add(compra)
    sesion.flush()
    sesion.add(
        LineaCompra(
            compra_id=compra.id,
            usuario_id=usuario.id,
            categoria_id=categoria.id if categoria else None,
            descripcion="Renglon",
            cantidad=1,
            precio_unitario=Decimal(total),
            subtotal=Decimal(total),
        )
    )
    sesion.commit()
    return compra


@pytest.fixture
def cinco_compras(
    sesion: Session, usuario: Usuario, otro_usuario: Usuario, super_y_farmacia, comercios
) -> list[Compra]:
    """Cinco compras del titular en setiembre, y una de otra persona que nunca debe aparecer."""
    supermercado, farmacia = super_y_farmacia
    walmart, fischel = comercios
    del_titular = [
        _compra(sesion, usuario, walmart, supermercado, date(2026, 9, 1), "10000"),
        _compra(sesion, usuario, walmart, supermercado, date(2026, 9, 5), "30000"),
        _compra(sesion, usuario, fischel, farmacia, date(2026, 9, 10), "5000"),
        _compra(sesion, usuario, fischel, None, date(2026, 9, 15), "20000", requiere_revision=True),
        _compra(sesion, usuario, walmart, supermercado, date(2026, 9, 20), "15000",
                estado=EstadoCompra.ANULADA, origen=OrigenCompra.INGESTA_CORREO),
    ]  # fmt: skip
    _compra(sesion, otro_usuario, walmart, None, date(2026, 9, 7), "99999")
    return del_titular


def _totales(respuesta) -> list[int]:
    return [int(Decimal(compra["total"])) for compra in respuesta.json()["contenido"]]


# ============================================================================
#  1 · Especificaciones
# ============================================================================


def test_la_especificacion_vacia_no_filtra() -> None:
    assert str(esp.Especificacion().como_predicado()) == "true"
    assert esp.entre_fechas(None, None).criterio is None
    assert esp.de_la_categoria(None).criterio is None
    assert esp.que_requieren_revision(None).criterio is None


def test_componer_con_la_vacia_devuelve_la_otra_tal_cual() -> None:
    del_titular = esp.del_titular(1)

    assert del_titular.y(esp.Especificacion()) is del_titular
    assert esp.Especificacion().y(del_titular) is del_titular
    assert esp.todas(esp.Especificacion(), del_titular, esp.en_estado(None)) is del_titular


def test_y_combina_con_and_y_o_combina_con_or() -> None:
    a, b = esp.del_titular(1), esp.en_estado(EstadoCompra.REGISTRADA)

    assert " AND " in str(a.y(b).como_predicado())
    assert " OR " in str(a.o(b).como_predicado())
    assert a.o(esp.Especificacion()).criterio is None, "«a, o cualquiera» es cualquiera"


def test_el_repositorio_recibe_una_sola_especificacion_ya_compuesta(
    sesion: Session, usuario: Usuario, cinco_compras: list[Compra], super_y_farmacia
) -> None:
    supermercado, _ = super_y_farmacia
    especificacion = esp.todas(
        esp.del_titular(usuario.id),
        esp.de_la_categoria(supermercado.id),
        esp.en_estado(EstadoCompra.REGISTRADA),
    )

    pagina = CompraRepository(sesion).buscar(
        especificacion, SolicitudDePagina(orden=(Orden("total"),))
    )

    assert [int(compra.total) for compra in pagina.contenido] == [10000, 30000]
    assert pagina.total_elementos == 2


# ============================================================================
#  2 · Servicio y metadatos
# ============================================================================


@pytest.mark.parametrize(
    "total, tamano, paginas", [(0, 20, 0), (1, 20, 1), (20, 20, 1), (21, 20, 2), (5, 2, 3)]
)
def test_el_total_de_paginas_redondea_hacia_arriba(total: int, tamano: int, paginas: int) -> None:
    assert Pagina([], pagina=0, tamano=tamano, total_elementos=total).total_paginas == paginas


def test_el_servicio_siempre_arranca_del_titular(
    sesion: Session, usuario: Usuario, otro_usuario: Usuario, cinco_compras: list[Compra]
) -> None:
    """La verificación de propiedad de una colección: sin filtros, solo lo propio."""
    servicio = CompraService(CompraRepository(sesion))

    propias = servicio.buscar_del_titular(usuario.id, FiltrosDeCompra(), SolicitudDePagina())
    ajenas = servicio.buscar_del_titular(otro_usuario.id, FiltrosDeCompra(), SolicitudDePagina())

    assert propias.total_elementos == 5
    assert {detalle.compra.usuario_id for detalle in propias.contenido} == {usuario.id}
    assert [int(detalle.compra.total) for detalle in ajenas.contenido] == [99999]


def test_un_rango_invertido_es_un_error_de_negocio(sesion: Session, usuario: Usuario) -> None:
    servicio = CompraService(CompraRepository(sesion))

    with pytest.raises(RangoInvalido):
        servicio.buscar_del_titular(
            usuario.id,
            FiltrosDeCompra(desde=date(2026, 9, 30), hasta=date(2026, 9, 1)),
            SolicitudDePagina(),
        )
    with pytest.raises(RangoInvalido):
        servicio.buscar_del_titular(
            usuario.id,
            FiltrosDeCompra(total_minimo=Decimal("500"), total_maximo=Decimal("100")),
            SolicitudDePagina(),
        )


# ============================================================================
#  3 · El endpoint
# ============================================================================


def test_la_pagina_trae_su_contenido_y_sus_metadatos(
    cliente: TestClient, cinco_compras: list[Compra]
) -> None:
    respuesta = cliente.get("/api/v1/compras", params={"tamano": 2})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {
        "contenido", "pagina", "tamano", "total_elementos", "total_paginas", "primera", "ultima",
        "orden",
    }  # fmt: skip
    assert len(cuerpo["contenido"]) == 2
    assert (cuerpo["pagina"], cuerpo["tamano"]) == (0, 2)
    assert (cuerpo["total_elementos"], cuerpo["total_paginas"]) == (5, 3)
    assert (cuerpo["primera"], cuerpo["ultima"]) == (True, False)
    assert cuerpo["orden"] == ["fecha,desc"], "el orden por defecto, declarado en la respuesta"


def test_recorrer_las_paginas_no_repite_ni_pierde_ninguna_compra(
    cliente: TestClient, cinco_compras: list[Compra]
) -> None:
    vistas: list[int] = []
    for pagina in range(3):
        cuerpo = cliente.get("/api/v1/compras", params={"tamano": 2, "pagina": pagina}).json()
        vistas += [compra["id"] for compra in cuerpo["contenido"]]
        assert cuerpo["ultima"] is (pagina == 2)

    assert sorted(vistas) == sorted(compra.id for compra in cinco_compras)
    assert len(set(vistas)) == 5


def test_una_pagina_mas_alla_del_final_viene_vacia_no_es_un_error(
    cliente: TestClient, cinco_compras: list[Compra]
) -> None:
    cuerpo = cliente.get("/api/v1/compras", params={"pagina": 9}).json()

    assert cuerpo["contenido"] == []
    assert cuerpo["total_elementos"] == 5


def test_sin_compras_la_coleccion_es_una_pagina_vacia(cliente: TestClient) -> None:
    cuerpo = cliente.get("/api/v1/compras").json()

    assert cuerpo["contenido"] == []
    assert (cuerpo["total_elementos"], cuerpo["total_paginas"]) == (0, 0)
    assert (cuerpo["primera"], cuerpo["ultima"]) == (True, True)


# ---- orden ----


def test_por_defecto_ordena_de_la_mas_reciente_a_la_mas_vieja(
    cliente: TestClient, cinco_compras: list[Compra]
) -> None:
    fechas = [c["fecha"] for c in cliente.get("/api/v1/compras").json()["contenido"]]

    assert fechas == sorted(fechas, reverse=True)


@pytest.mark.parametrize(
    "orden, esperado",
    [
        ("total,asc", [5000, 10000, 15000, 20000, 30000]),
        ("total,desc", [30000, 20000, 15000, 10000, 5000]),
        ("total", [5000, 10000, 15000, 20000, 30000]),  # sin sentido, ascendente
        ("fecha,asc", [10000, 30000, 5000, 20000, 15000]),
    ],
)
def test_orden_por_parametro(
    cliente: TestClient, cinco_compras: list[Compra], orden: str, esperado: list[int]
) -> None:
    respuesta = cliente.get("/api/v1/compras", params={"orden": orden})

    assert _totales(respuesta) == esperado


def test_se_puede_ordenar_por_varios_campos(
    sesion: Session, cliente: TestClient, usuario: Usuario, comercios
) -> None:
    walmart, _ = comercios
    for total in ("300", "100", "200"):
        _compra(sesion, usuario, walmart, None, date(2026, 9, 1), total)
    _compra(sesion, usuario, walmart, None, date(2026, 9, 2), "50")

    respuesta = cliente.get("/api/v1/compras", params={"orden": ["fecha,asc", "total,desc"]})

    assert _totales(respuesta) == [300, 200, 100, 50]
    assert respuesta.json()["orden"] == ["fecha,asc", "total,desc"]


@pytest.mark.parametrize("orden", ["contrasena_hash,asc", "total,arriba", "usuario_id", ""])
def test_ordenar_por_un_campo_que_no_esta_en_la_lista_da_400(
    cliente: TestClient, orden: str
) -> None:
    """El nombre del campo nunca llega a la consulta: solo se acepta uno de la lista cerrada."""
    respuesta = cliente.get("/api/v1/compras", params={"orden": orden})

    assert respuesta.status_code == 400
    (error,) = respuesta.json()["errores"]
    assert error["campo"] == "query.orden.0"
    assert "fecha, total, creado_en, id" in error["mensaje"]


@pytest.mark.parametrize("parametros", [{"pagina": -1}, {"tamano": 0}, {"tamano": 101}])
def test_una_pagina_o_un_tamano_fuera_de_rango_da_400(cliente: TestClient, parametros) -> None:
    assert cliente.get("/api/v1/compras", params=parametros).status_code == 400


# ---- filtros de negocio ----


def test_filtro_por_rango_de_fechas(cliente: TestClient, cinco_compras: list[Compra]) -> None:
    respuesta = cliente.get(
        "/api/v1/compras", params={"desde": "2026-09-05", "hasta": "2026-09-15", "orden": "fecha"}
    )

    assert _totales(respuesta) == [30000, 5000, 20000], "los dos extremos son inclusivos"
    assert respuesta.json()["total_elementos"] == 3


def test_filtro_por_categoria(cliente: TestClient, cinco_compras, super_y_farmacia) -> None:
    _, farmacia = super_y_farmacia

    respuesta = cliente.get("/api/v1/compras", params={"categoria_id": farmacia.id})

    assert _totales(respuesta) == [5000]
    assert respuesta.json()["contenido"][0]["categoria_nombre"] == "Farmacia"


def test_filtro_por_estado_origen_y_revision(cliente: TestClient, cinco_compras) -> None:
    assert _totales(cliente.get("/api/v1/compras", params={"estado": "ANULADA"})) == [15000]
    assert _totales(cliente.get("/api/v1/compras", params={"origen": "INGESTA_CORREO"})) == [15000]
    assert _totales(cliente.get("/api/v1/compras", params={"requiere_revision": True})) == [20000]
    sin_revision = cliente.get("/api/v1/compras", params={"requiere_revision": False}).json()
    assert sin_revision["total_elementos"] == 4


def test_filtro_por_comercio_y_por_rango_de_monto(
    cliente: TestClient, cinco_compras, comercios
) -> None:
    _, fischel = comercios

    por_comercio = cliente.get(
        "/api/v1/compras", params={"comercio_id": fischel.id, "orden": "total"}
    )
    por_monto = cliente.get(
        "/api/v1/compras",
        params={"total_minimo": "10000", "total_maximo": "20000", "orden": "total"},
    )

    assert _totales(por_comercio) == [5000, 20000]
    assert _totales(por_monto) == [10000, 15000, 20000]


def test_los_filtros_se_combinan_y_el_total_cuenta_solo_lo_filtrado(
    cliente: TestClient, cinco_compras, super_y_farmacia
) -> None:
    supermercado, _ = super_y_farmacia

    respuesta = cliente.get(
        "/api/v1/compras",
        params={
            "categoria_id": supermercado.id,
            "estado": "REGISTRADA",
            "desde": "2026-09-02",
            "tamano": 1,
        },
    )

    cuerpo = respuesta.json()
    assert _totales(respuesta) == [30000]
    assert (cuerpo["total_elementos"], cuerpo["total_paginas"]) == (1, 1)


def test_un_rango_de_fechas_invertido_da_422(cliente: TestClient) -> None:
    """Las dos fechas están bien formadas: lo que falla es la regla, no el formato."""
    respuesta = cliente.get(
        "/api/v1/compras", params={"desde": "2026-09-30", "hasta": "2026-09-01"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "RangoInvalido"


def test_una_fecha_mal_escrita_da_400(cliente: TestClient) -> None:
    assert cliente.get("/api/v1/compras", params={"desde": "ayer"}).status_code == 400


def test_la_compra_de_otro_titular_no_aparece_con_ningun_filtro(
    cliente: TestClient, cinco_compras
) -> None:
    respuesta = cliente.get("/api/v1/compras", params={"total_minimo": "90000"})

    assert respuesta.json()["contenido"] == []


# ---- las otras colecciones paginadas ----


def test_el_catalogo_de_comercios_se_pagina_y_se_filtra_por_nombre(
    cliente: TestClient, sesion: Session
) -> None:
    sesion.add_all(
        Comercio(nombre=nombre, nombre_normalizado=nombre.upper())
        for nombre in ("Walmart San Sebastian", "Walmart Heredia", "Fischel", "Automercado")
    )
    sesion.commit()

    pagina = cliente.get("/api/v1/comercios", params={"tamano": 3}).json()
    filtrada = cliente.get("/api/v1/comercios", params={"nombre": "walmárt"}).json()

    assert (pagina["total_elementos"], pagina["total_paginas"]) == (4, 2)
    assert [c["nombre"] for c in pagina["contenido"]] == [
        "Automercado", "Fischel", "Walmart Heredia",
    ]  # fmt: skip
    assert [c["nombre"] for c in filtrada["contenido"]] == [
        "Walmart Heredia", "Walmart San Sebastian",
    ]  # fmt: skip


def test_la_lista_de_cuentas_tambien_se_pagina(cliente_admin: TestClient, usuario: Usuario) -> None:
    cuerpo = cliente_admin.get(
        "/api/v1/usuarios", params={"tamano": 1, "orden": "correo,desc"}
    ).json()

    assert [cuenta["correo"] for cuenta in cuerpo["contenido"]] == [usuario.correo]
    assert (cuerpo["total_elementos"], cuerpo["total_paginas"]) == (2, 2)
