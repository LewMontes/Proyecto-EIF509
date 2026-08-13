"""Modelos de entrada y salida de la API (DTOs).

Viven en la capa de presentacion porque describen la FORMA DEL HTTP, no el
dominio. Las entidades de negocio estan en app.data.models y nunca se exponen
directamente: si lo hicieramos, cualquier cambio en la base romperia a los
clientes de la API.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SaludResponse(BaseModel):
    estado: str
    aplicacion: str
    version: str


class CrearCategoriaRequest(BaseModel):
    usuario_id: int = Field(gt=0)
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = Field(default=None, max_length=255)
    color_hex: str = Field(default="#6B7280", min_length=7, max_length=7)
    categoria_padre_id: int | None = None


class CategoriaResponse(BaseModel):
    # Permite construir la respuesta desde la entidad de SQLAlchemy.
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    nombre: str
    descripcion: str | None
    color_hex: str
    categoria_padre_id: int | None
    es_hoja: bool
    activa: bool


class ErrorResponse(BaseModel):
    detalle: str
