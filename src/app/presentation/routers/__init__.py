"""Routers de FastAPI: un archivo por recurso del contrato."""

from app.presentation.routers import (
    auth,
    categorias,
    comercios,
    compras,
    comprobantes,
    cuentas_correo,
    metodos_pago,
    presupuestos,
    reglas_categorizacion,
    salud,
    usuarios,
)

__all__ = [
    "auth",
    "categorias",
    "comercios",
    "compras",
    "comprobantes",
    "cuentas_correo",
    "metodos_pago",
    "presupuestos",
    "reglas_categorizacion",
    "salud",
    "usuarios",
]
