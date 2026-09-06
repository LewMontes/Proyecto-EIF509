"""Endpoints de Compra: listado, detalle, corrección manual y bitácora.

Antes de esto, `Compra` -el resultado real de conciliar un comprobante-
solo se podía "ver" indirectamente, a través de los campos planos de
`Comprobante` o de los eventos sueltos de su bitácora en Mongo. Nunca su
propio estado (`requiere_revision`, con qué método de pago y categoría
quedó). Estos endpoints son lo que la hace un dato de primera clase: se
puede listar, filtrar por "necesita revisión", ver en detalle, y corregir a
mano -y ahí sí, bajar hasta el comprobante que la generó (`/bitacora`, el
diferenciador declarado del dominio, ver ADR-002).
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.business.errors import RecursoNoEncontrado
from app.business.services.compra_service import CompraDetallada
from app.presentation.dependencies import (
    ServicioDeBitacora,
    ServicioDeCompras,
    ServicioDeConciliacion,
    VerificarTitular,
)
from app.presentation.schemas import (
    CompraResponse,
    EventoBitacoraResponse,
    GastoDeCategoriaResponse,
    ResolverRevisionCompraRequest,
)

router = APIRouter(prefix="/api/compras", tags=["compras"])


def _respuesta(detalle: CompraDetallada) -> CompraResponse:
    compra = detalle.compra
    return CompraResponse(
        id=compra.id,
        usuario_id=compra.usuario_id,
        comercio_id=compra.comercio_id,
        comercio_nombre=detalle.comercio_nombre,
        metodo_pago_id=compra.metodo_pago_id,
        metodo_pago_alias=detalle.metodo_pago_alias,
        categoria_id=detalle.categoria_id,
        categoria_nombre=detalle.categoria_nombre,
        fecha=compra.fecha,
        descripcion=compra.descripcion,
        moneda=compra.moneda,
        total=compra.total,
        total_moneda_base=compra.total_moneda_base,
        tipo_cambio_aplicado=compra.tipo_cambio_aplicado,
        estado=compra.estado,
        origen=compra.origen,
        requiere_revision=compra.requiere_revision,
        creado_en=compra.creado_en,
    )


@router.get(
    "", response_model=list[CompraResponse], summary="Listar las compras reales del titular"
)
def listar(
    servicio: ServicioDeCompras,
    _: VerificarTitular,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
    requiere_revision: bool | None = Query(
        default=None,
        description="True trae solo las que quedaron sin método de pago o sin categoría.",
    ),
    limite: int = Query(default=50, gt=0, le=200),
) -> list[CompraResponse]:
    return [
        _respuesta(detalle)
        for detalle in servicio.listar_del_titular(usuario_id, requiere_revision, limite)
    ]


@router.get(
    "/gasto-por-categoria",
    response_model=list[GastoDeCategoriaResponse],
    summary="En qué se le fue el mes al titular, por categoría",
)
def gasto_por_categoria(
    servicio: ServicioDeCompras,
    _: VerificarTitular,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
    anio: int = Query(ge=2000, le=2100),
    mes: int = Query(ge=1, le=12),
    # `Annotated` y no un default como los demás parámetros: con
    # `list[int] | None = Query(...)` ruff marca B008, porque una llamada en
    # el default de un parámetro de tipo lista es el patrón del default
    # mutable compartido. Acá FastAPI lo resuelve por petición y no hay tal
    # riesgo, pero la forma con `Annotated` lo deja explícito sin un `noqa`.
    categoria_id: Annotated[
        list[int] | None, Query(description="Repetible. Sin él, trae todas las categorías.")
    ] = None,
    metodo_pago_id: int | None = Query(default=None, gt=0),
    incluir_sin_categoria: bool = Query(default=True),
) -> list[GastoDeCategoriaResponse]:
    """El gasto del mes agrupado y sumado por la base, de mayor a menor.

    Va **antes** de `/{compra_id}` a propósito: FastAPI resuelve las rutas en
    orden de declaración, y si estuviera después, `gasto-por-categoria`
    entraría por la ruta del detalle y fallaría al no poder leerlo como un id.
    """
    filas = servicio.gasto_por_categoria_del_titular(
        usuario_id, anio, mes, categoria_id, metodo_pago_id, incluir_sin_categoria
    )
    return [
        GastoDeCategoriaResponse(
            categoria_id=fila.categoria_id,
            categoria_nombre=fila.categoria_nombre,
            total=fila.total,
            cantidad_de_renglones=fila.cantidad_de_renglones,
        )
        for fila in filas
    ]


@router.get("/{compra_id}", response_model=CompraResponse, summary="Detalle de una compra real")
def detalle(
    compra_id: int,
    servicio: ServicioDeCompras,
    _: VerificarTitular,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> CompraResponse:
    return _respuesta(servicio.obtener_detalle_del_titular(usuario_id, compra_id))


@router.post(
    "/{compra_id}/resolver",
    response_model=CompraResponse,
    summary="Corregir a mano el método de pago y/o la categoría de una compra",
)
def resolver(
    compra_id: int,
    peticion: ResolverRevisionCompraRequest,
    servicio: ServicioDeCompras,
    conciliacion: ServicioDeConciliacion,
    _: VerificarTitular,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> CompraResponse:
    conciliacion.resolver_revision(
        usuario_id, compra_id, peticion.metodo_pago_id, peticion.categoria_id
    )
    return _respuesta(servicio.obtener_detalle_del_titular(usuario_id, compra_id))


@router.get(
    "/{compra_id}/bitacora",
    response_model=list[EventoBitacoraResponse],
    summary="La trazabilidad completa de una compra: de qué correo nació y cómo se clasificó",
)
def bitacora_de_compra(
    compra_id: int,
    servicio: ServicioDeCompras,
    bitacora: ServicioDeBitacora,
    _: VerificarTitular,
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> list[EventoBitacoraResponse]:
    """Lista de eventos en el orden en que ocurrieron.

    404 si la compra no existe o no pertenece a este titular -verificado
    contra PostgreSQL, que sí sabe de quién es cada compra; Mongo no filtra
    por dueño por sí solo. También 404 si Mongo no tiene nada guardado para
    ella todavía -por ejemplo, si se conciliaron antes de que Mongo
    estuviera disponible.
    """
    servicio.obtener_del_titular(usuario_id, compra_id)
    eventos = bitacora.bitacora_de(compra_id)
    if eventos is None:
        raise RecursoNoEncontrado(f"No hay bitácora para la compra {compra_id}.")
    return [EventoBitacoraResponse(**evento) for evento in eventos]
