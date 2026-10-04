"""Endpoints de categorias.

El router no calcula ni valida reglas: traduce el JSON a un comando, llama al
servicio y traduce el resultado de vuelta a JSON. El titular sale siempre del
token, nunca de la peticion.
"""

from fastapi import APIRouter, Response, status

from app.business.services.categoria_service import (
    ActualizarCategoriaComando,
    CrearCategoriaComando,
)
from app.presentation.dependencies import ServicioDeCategorias, UsuarioActual
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import (
    ActualizarCategoriaRequest,
    CategoriaResponse,
    CrearCategoriaRequest,
    IdDeRuta,
)

router = APIRouter(prefix=f"{API_V1}/categorias", tags=["categorias"])


@router.post(
    "",
    response_model=CategoriaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una categoria",
)
def crear_categoria(
    peticion: CrearCategoriaRequest,
    servicio: ServicioDeCategorias,
    usuario: UsuarioActual,
    respuesta: Response,
) -> CategoriaResponse:
    """Crea una categoria del titular aplicando las reglas del dominio."""
    categoria = servicio.crear(
        CrearCategoriaComando(
            usuario_id=usuario.id,
            nombre=peticion.nombre,
            color_hex=peticion.color_hex,
            descripcion=peticion.descripcion,
            categoria_padre_id=peticion.categoria_padre_id,
        )
    )
    respuesta.headers["Location"] = ubicacion("categorias", categoria.id)
    return CategoriaResponse.model_validate(categoria)


@router.get(
    "",
    response_model=list[CategoriaResponse],
    summary="Listar las categorias activas del titular",
)
def listar_categorias(
    servicio: ServicioDeCategorias, usuario: UsuarioActual
) -> list[CategoriaResponse]:
    """Sin paginar a proposito: es un catalogo acotado -una cuenta tiene decenas
    de categorias, no miles- y el cliente lo necesita entero para armar el arbol."""
    categorias = servicio.listar_activas(usuario.id)
    return [CategoriaResponse.model_validate(categoria) for categoria in categorias]


@router.get("/{categoria_id}", response_model=CategoriaResponse, summary="Consultar una categoria")
def obtener_categoria(
    categoria_id: IdDeRuta, servicio: ServicioDeCategorias, usuario: UsuarioActual
) -> CategoriaResponse:
    return CategoriaResponse.model_validate(servicio.obtener(usuario.id, categoria_id))


@router.put(
    "/{categoria_id}",
    response_model=CategoriaResponse,
    summary="Reemplazar nombre, color y descripcion de una categoria",
)
def actualizar_categoria(
    categoria_id: IdDeRuta,
    peticion: ActualizarCategoriaRequest,
    servicio: ServicioDeCategorias,
    usuario: UsuarioActual,
) -> CategoriaResponse:
    """`PUT` y no `PATCH`: el cuerpo trae la representacion completa de lo editable,
    asi que repetir la misma peticion deja la categoria igual."""
    categoria = servicio.actualizar(
        ActualizarCategoriaComando(
            usuario_id=usuario.id,
            categoria_id=categoria_id,
            nombre=peticion.nombre,
            color_hex=peticion.color_hex,
            descripcion=peticion.descripcion,
        )
    )
    return CategoriaResponse.model_validate(categoria)


@router.delete(
    "/{categoria_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar una categoria",
)
def desactivar_categoria(
    categoria_id: IdDeRuta, servicio: ServicioDeCategorias, usuario: UsuarioActual
) -> None:
    """Borrado logico: la categoria deja de listarse, pero el gasto historico la conserva.

    `409` si todavia tiene subcategorias activas.
    """
    servicio.desactivar(usuario.id, categoria_id)
