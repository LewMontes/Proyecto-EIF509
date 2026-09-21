"""Endpoints del catálogo de comercios y su categoría sugerida por titular."""

from fastapi import APIRouter

from app.presentation.dependencies import (
    ServicioDeComercios,
    ServicioDeConciliacion,
)
from app.presentation.schemas import AsignarCategoriaComercioRequest, ComercioResponse

router = APIRouter(prefix="/api/comercios", tags=["comercios"])


@router.post(
    "/{comercio_id}/categoria",
    response_model=ComercioResponse,
    summary="Asignar o corregir la categoría sugerida de un comercio",
)
def asignar_categoria(
    # Sin cota superior a propósito -ver el comentario de _ID_MAXIMO en
    # schemas.py: un id de ruta absurdamente grande lo atrapa igual el
    # manejador de sqlalchemy.exc.DataError en main.py. Ponerle un `Path(...)`
    # acá obligaría a reordenar los parámetros (uno con default no puede ir
    # antes que uno sin default), y esa protección ya la da el manejador
    # global sin duplicar la cota en cada endpoint con un id en la ruta.
    comercio_id: int,
    peticion: AsignarCategoriaComercioRequest,
    servicio: ServicioDeComercios,
    conciliacion: ServicioDeConciliacion,
) -> ComercioResponse:
    """ "Corregir crea la regla": la próxima vez que este comercio aparezca en un
    comprobante de este mismo titular, esta es la categoría que se va a sugerir.
    No afecta a ningún otro titular que compre en el mismo comercio.

    También corrige lo que ya pasó: cualquier compra real de este comercio
    que ya se conciliara sin categoría queda categorizada con esta, y su
    presupuesto del período se acumula recién ahora -ver
    `ConciliacionService.recategorizar_compras_de_comercio`.
    """
    servicio.asignar_categoria(peticion.usuario_id, comercio_id, peticion.categoria_id)
    conciliacion.recategorizar_compras_de_comercio(
        peticion.usuario_id, comercio_id, peticion.categoria_id
    )
    return ComercioResponse.model_validate(servicio.obtener(comercio_id))
