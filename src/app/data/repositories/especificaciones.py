"""El patrón Specification: filtros de negocio que se componen.

Listar compras admite muchos filtros opcionales -por fechas, por categoría, por
comercio, por estado, por monto-, y cualquier combinación de ellos. Escrito
como un método del repositorio con un parámetro por filtro, cada filtro nuevo
agrega un parámetro y un `if`, y una segunda consulta que necesite los mismos
filtros los tiene que volver a escribir.

Una **especificación** es un filtro con nombre de negocio -«del titular»,
«entre estas fechas», «que requieren revisión»- encapsulado en un objeto que
sabe convertirse en un predicado SQL. Las especificaciones se combinan con `y`
y `o`, y el repositorio recibe una sola, ya compuesta, sin saber de cuántas
piezas está hecha.

Es el equivalente de `Specification<T>` de Spring Data: `toPredicate` es
`criterio`, y `and`/`or` son `y`/`o`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, or_, select, true

from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra, OrigenCompra
from app.data.models.linea_compra import LineaCompra


@dataclass(frozen=True)
class Especificacion:
    """Un filtro componible. Sin criterio, no filtra nada."""

    criterio: ColumnElement[bool] | None = None

    def y(self, otra: "Especificacion") -> "Especificacion":
        """Las dos a la vez. Una especificación vacía no cambia a la otra."""
        if self.criterio is None:
            return otra
        if otra.criterio is None:
            return self
        return Especificacion(and_(self.criterio, otra.criterio))

    def o(self, otra: "Especificacion") -> "Especificacion":
        """Cualquiera de las dos. Si una no filtra nada, el resultado tampoco."""
        if self.criterio is None or otra.criterio is None:
            return Especificacion()
        return Especificacion(or_(self.criterio, otra.criterio))

    def como_predicado(self) -> ColumnElement[bool]:
        """El predicado para el `WHERE`. La especificación vacía es `TRUE`."""
        return self.criterio if self.criterio is not None else true()


def todas(*especificaciones: Especificacion) -> Especificacion:
    """La conjunción de varias especificaciones."""
    resultado = Especificacion()
    for especificacion in especificaciones:
        resultado = resultado.y(especificacion)
    return resultado


# ---- especificaciones de Compra ----
#
# Cada función recibe el valor del filtro y devuelve la especificación. Con
# `None` devuelve la vacía: un filtro que el cliente no mandó no filtra, en vez
# de filtrar por nulo.


def del_titular(usuario_id: int) -> Especificacion:
    """Las compras de ese titular. Es la única que nunca es opcional.

    El aislamiento entre cuentas pasa por acá: toda búsqueda de compras
    arranca de esta especificación, y las demás se le suman.
    """
    return Especificacion(Compra.usuario_id == usuario_id)


def entre_fechas(desde: date | None, hasta: date | None) -> Especificacion:
    """Compras hechas entre dos fechas, ambas inclusive. Cualquiera de las dos puede faltar."""
    return todas(
        Especificacion(Compra.fecha >= desde) if desde is not None else Especificacion(),
        Especificacion(Compra.fecha <= hasta) if hasta is not None else Especificacion(),
    )


def de_la_categoria(categoria_id: int | None) -> Especificacion:
    """Compras con **algún renglón** en esa categoría.

    La categoría vive en `LineaCompra`, no en `Compra`: una compra desglosada
    puede tener renglones de categorías distintas. Por eso es una subconsulta
    y no un `JOIN` -con un `JOIN`, una compra con dos renglones de la misma
    categoría saldría dos veces y descuadraría el conteo de la página.
    """
    if categoria_id is None:
        return Especificacion()
    return Especificacion(
        Compra.id.in_(select(LineaCompra.compra_id).where(LineaCompra.categoria_id == categoria_id))
    )


def del_comercio(comercio_id: int | None) -> Especificacion:
    """Compras hechas en ese comercio."""
    return Especificacion(Compra.comercio_id == comercio_id) if comercio_id else Especificacion()


def con_metodo_de_pago(metodo_pago_id: int | None) -> Especificacion:
    """Compras pagadas con ese método de pago."""
    if metodo_pago_id is None:
        return Especificacion()
    return Especificacion(Compra.metodo_pago_id == metodo_pago_id)


def en_estado(estado: EstadoCompra | None) -> Especificacion:
    """Compras en ese estado del ciclo de vida."""
    return Especificacion(Compra.estado == estado) if estado is not None else Especificacion()


def de_origen(origen: OrigenCompra | None) -> Especificacion:
    """Compras según de dónde nacieron: capturadas a mano o ingeridas por correo."""
    return Especificacion(Compra.origen == origen) if origen is not None else Especificacion()


def que_requieren_revision(requiere_revision: bool | None) -> Especificacion:
    """Las que quedaron sin método de pago o sin categoría (o las que no)."""
    if requiere_revision is None:
        return Especificacion()
    return Especificacion(Compra.requiere_revision.is_(requiere_revision))


def con_total_entre(minimo: Decimal | None, maximo: Decimal | None) -> Especificacion:
    """Compras cuyo total **en moneda base** cae en ese rango.

    Sobre `total_moneda_base` y no sobre `total`: comparar contra el total
    crudo pondría en la misma bolsa 50 dólares y 50 colones.
    """
    return todas(
        Especificacion(Compra.total_moneda_base >= minimo)
        if minimo is not None
        else Especificacion(),
        Especificacion(Compra.total_moneda_base <= maximo)
        if maximo is not None
        else Especificacion(),
    )
