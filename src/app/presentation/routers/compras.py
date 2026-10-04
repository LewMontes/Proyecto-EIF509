"""Endpoints de Compra: el Proceso 1 del dominio y todo lo que se le hace a una compra.

`POST /compras` **es** el Proceso 1 -la captura manual con desglose-. El resto
son las operaciones sobre una compra que ya existe, haya nacido de ese proceso
o de la ingesta de un comprobante (Proceso 2): consultarla, corregirla,
anularla, y bajar hasta su trazabilidad.

Los recursos son sustantivos y la operación la dice el verbo HTTP: corregir es
`PATCH /compras/{id}`, anular es `DELETE /compras/{id}`. No hay
`/compras/{id}/resolver` ni `/compras/{id}/anular`.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.business.errors import RecursoNoEncontrado
from app.business.services.compra_service import CompraDetallada
from app.business.services.registrar_compra_service import (
    CompraRegistrada,
    LineaDeCompraComando,
    RegistrarCompraComando,
)
from app.presentation.dependencies import (
    ServicioDeBitacora,
    ServicioDeCompras,
    ServicioDeConciliacion,
    ServicioDeRegistroDeCompras,
    UsuarioActual,
)
from app.presentation.rutas import API_V1, ubicacion
from app.presentation.schemas import (
    CompraRegistradaResponse,
    CompraResponse,
    CorregirCompraRequest,
    EventoBitacoraResponse,
    GastoDeCategoriaResponse,
    IdDeRuta,
    LineaCompraResponse,
    RegistrarCompraRequest,
)

router = APIRouter(prefix=f"{API_V1}/compras", tags=["compras"])


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


def _respuesta_registrada(registrada: CompraRegistrada) -> CompraRegistradaResponse:
    """Mapeo manual del DTO del negocio al del contrato HTTP.

    Explícito y no `model_validate` a propósito: es el punto donde se ve, de
    un vistazo, que lo que sale del servicio ya es un DTO -ninguna entidad de
    SQLAlchemy cruza esta función.
    """
    return CompraRegistradaResponse(
        compra_id=registrada.compra_id,
        fecha=registrada.fecha,
        comercio_nombre=registrada.comercio_nombre,
        metodo_pago_alias=registrada.metodo_pago_alias,
        moneda=registrada.moneda,
        estado=registrada.estado,
        subtotal=registrada.subtotal,
        descuento=registrada.descuento,
        impuesto=registrada.impuesto,
        total=registrada.total,
        tipo_cambio_aplicado=registrada.tipo_cambio_aplicado,
        total_moneda_base=registrada.total_moneda_base,
        lineas=[
            LineaCompraResponse(
                linea_id=linea.linea_id,
                descripcion=linea.descripcion,
                cantidad=linea.cantidad,
                precio_unitario=linea.precio_unitario,
                descuento=linea.descuento,
                exento_impuesto=linea.exento_impuesto,
                subtotal=linea.subtotal,
                impuesto=linea.impuesto,
                categoria_id=linea.categoria_id,
                categoria_nombre=linea.categoria_nombre,
                categorizada_automaticamente=linea.categorizada_automaticamente,
            )
            for linea in registrada.lineas
        ],
        presupuestos_alertados=list(registrada.presupuestos_alertados),
    )


@router.post(
    "",
    response_model=CompraRegistradaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar a mano una compra con su desglose por renglón (Proceso 1)",
)
def registrar(
    peticion: RegistrarCompraRequest,
    servicio: ServicioDeRegistroDeCompras,
    usuario: UsuarioActual,
    respuesta: Response,
) -> CompraRegistradaResponse:
    """El Proceso 1 del dominio: la compra que no llegó por correo.

    El cuerpo trae el desglose completo; el servicio calcula subtotales,
    impuesto y totales, categoriza los renglones que el titular dejó sin
    categoría, e impacta el presupuesto de cada categoría afectada -todo en
    una sola transacción.
    """
    registrada = servicio.registrar(
        RegistrarCompraComando(
            usuario_id=usuario.id,
            comercio_id=peticion.comercio_id,
            fecha=peticion.fecha,
            lineas=tuple(
                LineaDeCompraComando(
                    descripcion=linea.descripcion,
                    cantidad=linea.cantidad,
                    precio_unitario=linea.precio_unitario,
                    descuento=linea.descuento,
                    exento_impuesto=linea.exento_impuesto,
                    categoria_id=linea.categoria_id,
                )
                for linea in peticion.lineas
            ),
            moneda=peticion.moneda,
            metodo_pago_id=peticion.metodo_pago_id,
            descripcion=peticion.descripcion,
            descuento=peticion.descuento,
            total_declarado=peticion.total_declarado,
            tipo_cambio_aplicado=peticion.tipo_cambio_aplicado,
        )
    )
    respuesta.headers["Location"] = ubicacion("compras", registrada.compra_id)
    return _respuesta_registrada(registrada)


@router.get("", response_model=list[CompraResponse], summary="Listar las compras del titular")
def listar(
    servicio: ServicioDeCompras,
    usuario: UsuarioActual,
    requiere_revision: bool | None = Query(
        default=None,
        description="True trae solo las que quedaron sin método de pago o sin categoría.",
    ),
    limite: int = Query(default=50, gt=0, le=200),
) -> list[CompraResponse]:
    return [
        _respuesta(detalle)
        for detalle in servicio.listar_del_titular(usuario.id, requiere_revision, limite)
    ]


@router.get(
    "/gasto-por-categoria",
    response_model=list[GastoDeCategoriaResponse],
    summary="En qué se le fue el mes al titular, por categoría",
)
def gasto_por_categoria(
    servicio: ServicioDeCompras,
    usuario: UsuarioActual,
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
        usuario.id, anio, mes, categoria_id, metodo_pago_id, incluir_sin_categoria
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


@router.get("/{compra_id}", response_model=CompraResponse, summary="Detalle de una compra")
def detalle(
    compra_id: IdDeRuta, servicio: ServicioDeCompras, usuario: UsuarioActual
) -> CompraResponse:
    """`404` si la compra no existe **o es de otro titular**: el servicio la busca
    por id y por dueño a la vez, así que una ajena es indistinguible de una que
    no existe."""
    return _respuesta(servicio.obtener_detalle_del_titular(usuario.id, compra_id))


@router.patch(
    "/{compra_id}",
    response_model=CompraResponse,
    summary="Corregir el método de pago y/o la categoría de una compra",
)
def corregir(
    compra_id: IdDeRuta,
    peticion: CorregirCompraRequest,
    servicio: ServicioDeCompras,
    conciliacion: ServicioDeConciliacion,
    usuario: UsuarioActual,
) -> CompraResponse:
    """La corrección manual de una compra que quedó `requiere_revision`.

    `PATCH` porque es una modificación parcial: solo se toca lo que viene en
    el cuerpo. El titular confirma o corrige, y esa corrección es la que hace
    aprender al sistema. `409` si la compra está anulada.
    """
    conciliacion.resolver_revision(
        usuario.id, compra_id, peticion.metodo_pago_id, peticion.categoria_id
    )
    return _respuesta(servicio.obtener_detalle_del_titular(usuario.id, compra_id))


@router.delete("/{compra_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Anular una compra")
def anular(
    compra_id: IdDeRuta, conciliacion: ServicioDeConciliacion, usuario: UsuarioActual
) -> None:
    """Anula la compra y le devuelve su monto a los presupuestos que había impactado.

    Nunca se borra físicamente: queda `ANULADA`, sigue consultable y deja de
    contar como gasto. `409` si ya estaba anulada.
    """
    conciliacion.anular(usuario.id, compra_id)


@router.get(
    "/{compra_id}/bitacora",
    response_model=list[EventoBitacoraResponse],
    summary="La trazabilidad completa de una compra: de dónde nació y cómo se clasificó",
)
def bitacora_de_compra(
    compra_id: IdDeRuta,
    servicio: ServicioDeCompras,
    bitacora: ServicioDeBitacora,
    usuario: UsuarioActual,
) -> list[EventoBitacoraResponse]:
    """Lista de eventos en el orden en que ocurrieron.

    404 si la compra no existe o no pertenece a este titular -verificado
    contra PostgreSQL, que sí sabe de quién es cada compra; Mongo no filtra
    por dueño por sí solo. También 404 si Mongo no tiene nada guardado para
    ella todavía.
    """
    servicio.obtener_del_titular(usuario.id, compra_id)
    eventos = bitacora.bitacora_de(compra_id)
    if eventos is None:
        raise RecursoNoEncontrado(f"No hay bitácora para la compra {compra_id}.")
    return [EventoBitacoraResponse(**evento) for evento in eventos]
