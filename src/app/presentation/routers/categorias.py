"""Endpoints de categorias.

El router no calcula ni valida reglas: traduce el JSON a un comando, llama al
servicio y traduce el resultado de vuelta a JSON.
"""

from fastapi import APIRouter, Query, status

from app.business.services.categoria_service import CrearCategoriaComando
from app.presentation.dependencies import (
    ServicioDeCategorias,
)
from app.presentation.schemas import CategoriaResponse, CrearCategoriaRequest

router = APIRouter(prefix="/api/categorias", tags=["categorias"])


@router.post(
    "",
    response_model=CategoriaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una categoria",
)
def crear_categoria(
    peticion: CrearCategoriaRequest,
    servicio: ServicioDeCategorias,
) -> CategoriaResponse:
    """Crea una categoria aplicando las reglas del dominio."""
    comando = CrearCategoriaComando(
        usuario_id=peticion.usuario_id,
        nombre=peticion.nombre,
        color_hex=peticion.color_hex,
        descripcion=peticion.descripcion,
        categoria_padre_id=peticion.categoria_padre_id,
    )
    categoria = servicio.crear(comando)
    return CategoriaResponse.model_validate(categoria)


@router.get(
    "",
    response_model=list[CategoriaResponse],
    summary="Listar las categorias activas de un usuario",
)
def listar_categorias(
    servicio: ServicioDeCategorias,
    usuario_id: int = Query(
        gt=0, le=2_147_483_647, description="Titular cuyas categorias se listan"
    ),
) -> list[CategoriaResponse]:
    """Lista las categorias activas del titular indicado."""
    categorias = servicio.listar_activas(usuario_id)
    return [CategoriaResponse.model_validate(categoria) for categoria in categorias]
