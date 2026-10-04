"""Endpoints del catálogo de comercios y su categoría sugerida por titular.

El catálogo es **compartido** entre todos los titulares, y por eso es donde los
dos roles se separan más claro:

- Leerlo lo puede hacer cualquier cuenta autenticada.
- Darlo de alta a mano es de `ADMIN`: un titular no escribe en algo que es de
  todos. (La ingesta sí crea comercios nuevos al conciliar, pero lo hace el
  sistema, no una persona eligiendo el nombre.)
- La categoría sugerida no es del catálogo: es de cada titular, así que la
  asigna el titular para sí mismo.
"""

from fastapi import APIRouter, Response, status

from app.presentation.dependencies import (
    Administrador,
    ServicioDeComercios,
    ServicioDeConciliacion,
    UsuarioActual,
)
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import (
    AsignarCategoriaComercioRequest,
    ComercioResponse,
    CrearComercioRequest,
    IdDeRuta,
)

router = APIRouter(prefix=f"{API_V1}/comercios", tags=["comercios"])


@router.post(
    "",
    response_model=ComercioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta un comercio en el catálogo compartido",
)
def crear(
    peticion: CrearComercioRequest,
    servicio: ServicioDeComercios,
    _: Administrador,
    respuesta: Response,
) -> ComercioResponse:
    """Solo `ADMIN`: un titular que lo intenta recibe `403`."""
    comercio = servicio.crear(
        peticion.nombre, peticion.identificacion_tributaria, peticion.provincia
    )
    respuesta.headers["Location"] = ubicacion("comercios", comercio.id)
    return ComercioResponse.model_validate(comercio)


@router.get("", response_model=list[ComercioResponse], summary="Listar el catálogo de comercios")
def listar(servicio: ServicioDeComercios, _: UsuarioActual) -> list[ComercioResponse]:
    return [ComercioResponse.model_validate(comercio) for comercio in servicio.listar()]


@router.get("/{comercio_id}", response_model=ComercioResponse, summary="Consultar un comercio")
def obtener(
    comercio_id: IdDeRuta, servicio: ServicioDeComercios, _: UsuarioActual
) -> ComercioResponse:
    return ComercioResponse.model_validate(servicio.obtener(comercio_id))


@router.put(
    "/{comercio_id}/categoria-sugerida",
    response_model=ComercioResponse,
    summary="Asignar o corregir la categoría que el titular le sugiere a un comercio",
)
def asignar_categoria(
    comercio_id: IdDeRuta,
    peticion: AsignarCategoriaComercioRequest,
    servicio: ServicioDeComercios,
    conciliacion: ServicioDeConciliacion,
    usuario: UsuarioActual,
) -> ComercioResponse:
    """ "Corregir crea la regla": la próxima vez que este comercio aparezca en un
    comprobante de este mismo titular, esta es la categoría que se va a sugerir.
    No afecta a ningún otro titular que compre en el mismo comercio.

    `PUT` porque es idempotente: la sugerencia es un sub-recurso único por
    (titular, comercio), y asignarla dos veces la deja igual.

    También corrige lo que ya pasó: cualquier compra real de este comercio
    que ya se conciliara sin categoría queda categorizada con esta, y su
    presupuesto del período se acumula recién ahora -ver
    `ConciliacionService.recategorizar_compras_de_comercio`.
    """
    servicio.asignar_categoria(usuario.id, comercio_id, peticion.categoria_id)
    conciliacion.recategorizar_compras_de_comercio(usuario.id, comercio_id, peticion.categoria_id)
    return ComercioResponse.model_validate(servicio.obtener(comercio_id))
