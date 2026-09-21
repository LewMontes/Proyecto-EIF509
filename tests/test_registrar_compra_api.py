"""El Proceso 1 desde la API: POST /api/compras.

Las reglas del servicio se prueban en `test_registrar_compra_service.py`; acá
solo lo que agrega la capa de presentación -que la validación de forma corte
antes de llegar al negocio, que los errores del dominio lleguen traducidos, y
que la respuesta sea el DTO y no la entidad.
"""

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.business.services.comercio_service import ComercioService
from app.data.models.usuario import Usuario
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository


def _comercio_y_categoria(cliente: TestClient, usuario: Usuario, sesion: Session):
    """Un comercio del catálogo y una categoría hoja del titular, vía la API."""
    respuesta = cliente.post(
        "/api/categorias",
        json={"usuario_id": usuario.id, "nombre": "Supermercado", "color_hex": "#2563EB"},
    )
    assert respuesta.status_code == 201
    categoria_id = respuesta.json()["id"]

    comercio = ComercioService(
        ComercioRepository(sesion), ComercioCategoriaRepository(sesion), CategoriaRepository(sesion)
    ).resolver_o_crear("Walmart San Sebastián")
    return comercio.id, categoria_id


def test_registrar_una_compra_manual_devuelve_el_desglose_calculado(
    cliente: TestClient, usuario: Usuario, sesion: Session
) -> None:
    comercio_id, categoria_id = _comercio_y_categoria(cliente, usuario, sesion)

    respuesta = cliente.post(
        "/api/compras",
        json={
            "usuario_id": usuario.id,
            "comercio_id": comercio_id,
            "fecha": "2026-08-30",
            "lineas": [
                {
                    "descripcion": "Leche 1L",
                    "cantidad": "2",
                    "precio_unitario": "1000.00",
                    "categoria_id": categoria_id,
                }
            ],
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert Decimal(cuerpo["subtotal"]) == Decimal("2000.00")
    assert Decimal(cuerpo["impuesto"]) == Decimal("260.00")
    assert Decimal(cuerpo["total"]) == Decimal("2260.00")
    assert cuerpo["estado"] == "REGISTRADA"
    assert cuerpo["lineas"][0]["categoria_nombre"] == "Supermercado"
    # Ninguna entidad de SQLAlchemy cruzó la frontera: la respuesta trae
    # exactamente los campos del DTO, ni uno más.
    assert "usuario_id" not in cuerpo


def test_registrar_una_compra_sin_renglones_da_422(
    cliente: TestClient, usuario: Usuario, sesion: Session
) -> None:
    """La lista vacía la rechaza Pydantic (`min_length=1`) antes de llegar al
    servicio: es forma del dato, no regla de negocio."""
    comercio_id, _ = _comercio_y_categoria(cliente, usuario, sesion)

    respuesta = cliente.post(
        "/api/compras",
        json={
            "usuario_id": usuario.id,
            "comercio_id": comercio_id,
            "fecha": "2026-08-30",
            "lineas": [],
        },
    )

    assert respuesta.status_code == 422


def test_una_categoria_padre_da_409(cliente: TestClient, usuario: Usuario, sesion: Session) -> None:
    """El error de negocio llega traducido por `main.py`, no crudo."""
    comercio_id, categoria_id = _comercio_y_categoria(cliente, usuario, sesion)
    # Colgarle una hija convierte a "Supermercado" en categoría padre.
    cliente.post(
        "/api/categorias",
        json={
            "usuario_id": usuario.id,
            "nombre": "Abarrotes",
            "color_hex": "#111111",
            "categoria_padre_id": categoria_id,
        },
    )

    respuesta = cliente.post(
        "/api/compras",
        json={
            "usuario_id": usuario.id,
            "comercio_id": comercio_id,
            "fecha": "2026-08-30",
            "lineas": [
                {
                    "descripcion": "Leche 1L",
                    "cantidad": "1",
                    "precio_unitario": "1000.00",
                    "categoria_id": categoria_id,
                }
            ],
        },
    )

    assert respuesta.status_code == 409
    assert "padre" in respuesta.json()["detalle"]
