"""Endpoints de categorias.

El controlador hace tres cosas y ninguna mas: traduce el JSON a un comando,
llama al servicio y traduce el resultado. Ni una regla ni una consulta viven aqui.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.business.services.categoria_service import CrearCategoriaComando
from app.presentation.dependencies import ServicioCategoria
from app.presentation.schemas import CategoriaResponse, CrearCategoriaRequest

router = APIRouter(prefix="/api/categorias", tags=["categorias"])


@router.post("", response_model=CategoriaResponse, status_code=status.HTTP_201_CREATED)
def crear_categoria(
    peticion: CrearCategoriaRequest,
    servicio: ServicioCategoria,
) -> CategoriaResponse:
    categoria = servicio.crear(
        CrearCategoriaComando(
            usuario_id=peticion.usuario_id,
            nombre=peticion.nombre,
            descripcion=peticion.descripcion,
            color_hex=peticion.color_hex,
            categoria_padre_id=peticion.categoria_padre_id,
        )
    )
    return CategoriaResponse.model_validate(categoria)


@router.get("", response_model=list[CategoriaResponse])
def listar_categorias(
    usuario_id: int,
    servicio: ServicioCategoria,
) -> list[CategoriaResponse]:
    return [CategoriaResponse.model_validate(c) for c in servicio.listar(usuario_id)]
