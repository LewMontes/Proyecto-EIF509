"""El Proceso 1 desde la API -`POST /api/v1/compras`- y las operaciones sobre una compra.

Las reglas del servicio se prueban en `test_registrar_compra_service.py`; acá
solo lo que agrega la capa de presentación -que la validación de forma corte
antes de llegar al negocio, que los errores del dominio lleguen traducidos, y
que la respuesta sea el DTO y no la entidad.
"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.business.services.comercio_service import ComercioService
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository


def _comercio_y_categoria(cliente: TestClient, sesion: Session) -> tuple[int, int]:
    """Un comercio del catálogo y una categoría hoja del titular."""
    respuesta = cliente.post(
        "/api/v1/categorias", json={"nombre": "Supermercado", "color_hex": "#2563EB"}
    )
    assert respuesta.status_code == 201
    comercio = ComercioService(
        ComercioRepository(sesion), ComercioCategoriaRepository(sesion), CategoriaRepository(sesion)
    ).resolver_o_crear("Walmart San Sebastián")
    return comercio.id, respuesta.json()["id"]


def _compra(comercio_id: int, categoria_id: int | None, **extra) -> dict:
    linea = {"descripcion": "Leche 1L", "cantidad": "2", "precio_unitario": "1000.00"}
    if categoria_id is not None:
        linea["categoria_id"] = categoria_id
    return {"comercio_id": comercio_id, "fecha": "2026-08-30", "lineas": [linea], **extra}


def test_registrar_una_compra_manual_devuelve_201_con_location_y_el_desglose(
    cliente: TestClient, sesion: Session
) -> None:
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)

    respuesta = cliente.post("/api/v1/compras", json=_compra(comercio_id, categoria_id))

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert respuesta.headers["Location"] == f"/api/v1/compras/{cuerpo['compra_id']}"
    assert Decimal(cuerpo["subtotal"]) == Decimal("2000.00")
    assert Decimal(cuerpo["impuesto"]) == Decimal("260.00")
    assert Decimal(cuerpo["total"]) == Decimal("2260.00")
    assert cuerpo["estado"] == "REGISTRADA"
    assert cuerpo["lineas"][0]["categoria_nombre"] == "Supermercado"
    # Ninguna entidad de SQLAlchemy cruzó la frontera: la respuesta trae
    # exactamente los campos del DTO, ni uno más.
    assert "usuario_id" not in cuerpo

    detalle = cliente.get(respuesta.headers["Location"])
    assert detalle.status_code == 200
    assert detalle.json()["origen"] == "MANUAL"


def test_una_fecha_futura_da_422(cliente: TestClient, sesion: Session) -> None:
    """La forma es válida -es una fecha-; lo que falla es la regla del dominio."""
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)
    manana = (date.today() + timedelta(days=1)).isoformat()

    respuesta = cliente.post(
        "/api/v1/compras", json=_compra(comercio_id, categoria_id, fecha=manana)
    )

    assert respuesta.status_code == 422
    assert "futura" in respuesta.json()["detail"]


def test_una_categoria_padre_da_409(cliente: TestClient, sesion: Session) -> None:
    """El error de negocio llega traducido, no crudo."""
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)
    # Colgarle una hija convierte a "Supermercado" en categoría padre.
    cliente.post(
        "/api/v1/categorias",
        json={"nombre": "Abarrotes", "color_hex": "#111111", "categoria_padre_id": categoria_id},
    )

    respuesta = cliente.post("/api/v1/compras", json=_compra(comercio_id, categoria_id))

    assert respuesta.status_code == 409
    assert "padre" in respuesta.json()["detail"]


def test_un_total_que_no_cuadra_con_el_recibo_da_409(cliente: TestClient, sesion: Session) -> None:
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)

    respuesta = cliente.post(
        "/api/v1/compras", json=_compra(comercio_id, categoria_id, total_declarado="9999.00")
    )

    assert respuesta.status_code == 409
    assert "no cuadra" in respuesta.json()["detail"]


def test_un_comercio_que_no_existe_da_404(cliente: TestClient, sesion: Session) -> None:
    _, categoria_id = _comercio_y_categoria(cliente, sesion)

    assert cliente.post("/api/v1/compras", json=_compra(999999, categoria_id)).status_code == 404


def test_la_compra_de_otro_titular_da_404(
    aplicacion, cliente: TestClient, otro_usuario, sesion: Session
) -> None:
    from tests.conftest import cabecera_de

    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)
    compra_id = cliente.post("/api/v1/compras", json=_compra(comercio_id, categoria_id)).json()[
        "compra_id"
    ]
    intruso = TestClient(aplicacion, headers=cabecera_de(otro_usuario))

    assert intruso.get(f"/api/v1/compras/{compra_id}").status_code == 404
    assert intruso.delete(f"/api/v1/compras/{compra_id}").status_code == 404
    assert (
        intruso.patch(
            f"/api/v1/compras/{compra_id}", json={"categoria_id": categoria_id}
        ).status_code
        == 404
    )
    assert intruso.get("/api/v1/compras").json()["contenido"] == []


def test_anular_una_compra_da_204_y_devuelve_el_monto_al_presupuesto(
    cliente: TestClient, sesion: Session
) -> None:
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)
    presupuesto = cliente.post(
        "/api/v1/presupuestos",
        json={
            "categoria_id": categoria_id,
            "anio": 2026,
            "mes": 8,
            "moneda": "CRC",
            "monto_limite": "100000.00",
        },
    ).json()
    compra_id = cliente.post("/api/v1/compras", json=_compra(comercio_id, categoria_id)).json()[
        "compra_id"
    ]
    ruta_presupuesto = f"/api/v1/presupuestos/{presupuesto['id']}"
    assert Decimal(cliente.get(ruta_presupuesto).json()["monto_consumido"]) == Decimal("2260.00")

    respuesta = cliente.delete(f"/api/v1/compras/{compra_id}")

    assert respuesta.status_code == 204
    assert Decimal(cliente.get(ruta_presupuesto).json()["monto_consumido"]) == Decimal("0")
    # Nunca se borra: sigue consultable, ya anulada.
    assert cliente.get(f"/api/v1/compras/{compra_id}").json()["estado"] == "ANULADA"
    # Y anularla dos veces choca con su estado.
    assert cliente.delete(f"/api/v1/compras/{compra_id}").status_code == 409


def test_corregir_una_compra_con_patch(cliente: TestClient, sesion: Session) -> None:
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)
    compra_id = cliente.post("/api/v1/compras", json=_compra(comercio_id, categoria_id)).json()[
        "compra_id"
    ]
    metodo = cliente.post(
        "/api/v1/metodos-pago", json={"alias": "Efectivo", "tipo": "EFECTIVO"}
    ).json()

    respuesta = cliente.patch(f"/api/v1/compras/{compra_id}", json={"metodo_pago_id": metodo["id"]})

    assert respuesta.status_code == 200
    assert respuesta.json()["metodo_pago_alias"] == "Efectivo"
    assert respuesta.json()["categoria_id"] == categoria_id, "lo que no se manda no se toca"


def test_la_bitacora_de_una_compra_sin_eventos_da_404(cliente: TestClient, sesion: Session) -> None:
    comercio_id, categoria_id = _comercio_y_categoria(cliente, sesion)
    compra_id = cliente.post("/api/v1/compras", json=_compra(comercio_id, categoria_id)).json()[
        "compra_id"
    ]

    assert cliente.get(f"/api/v1/compras/{compra_id}/bitacora").status_code == 404
    assert cliente.get("/api/v1/compras/999999/bitacora").status_code == 404
