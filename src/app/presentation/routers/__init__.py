"""Routers de FastAPI: un archivo por area del dominio."""

from app.presentation.routers import (
    categorias,
    comercios,
    compras,
    metodos_pago,
    presupuestos,
    reglas_categorizacion,
    salud,
)

__all__ = [
    "categorias",
    "comercios",
    "compras",
    "metodos_pago",
    "presupuestos",
    "reglas_categorizacion",
    "salud",
]
