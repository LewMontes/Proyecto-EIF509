"""Paginación y orden de una consulta: el equivalente de `Pageable` y `Page`.

Una colección que puede crecer sin límite -las compras de un titular, sus
comprobantes, el catálogo de comercios- no se devuelve entera: se pide de a
páginas. Este módulo tiene las tres piezas que hacen falta, y nada más:

- `SolicitudDePagina` · qué página, de qué tamaño y en qué orden (`Pageable`).
- `Pagina` · el contenido de esa página **con sus metadatos** (`Page`).
- `paginar` · la función que convierte un `SELECT` cualquiera en una `Pagina`.

Vive en la capa de datos porque es donde se arma el `LIMIT`/`OFFSET`, pero no
depende de ninguna entidad: sirve igual para cualquier repositorio.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

TAMANO_POR_DEFECTO = 20
TAMANO_MAXIMO = 100


@dataclass(frozen=True)
class Orden:
    """Un criterio de orden: por qué campo y en qué sentido."""

    campo: str
    descendente: bool = False


@dataclass(frozen=True)
class SolicitudDePagina:
    """Lo que el cliente pide: la página (desde 0), su tamaño y el orden."""

    pagina: int = 0
    tamano: int = TAMANO_POR_DEFECTO
    orden: tuple[Orden, ...] = ()

    @property
    def desplazamiento(self) -> int:
        return self.pagina * self.tamano


@dataclass(frozen=True)
class Pagina[T]:
    """Una página de resultados, con lo que el cliente necesita para pedir la siguiente."""

    contenido: list[T]
    pagina: int
    tamano: int
    total_elementos: int
    orden: tuple[Orden, ...] = ()

    @property
    def total_paginas(self) -> int:
        """Cuántas páginas hay en total. Cero elementos son cero páginas."""
        return -(-self.total_elementos // self.tamano)  # división hacia arriba

    @property
    def es_primera(self) -> bool:
        return self.pagina == 0

    @property
    def es_ultima(self) -> bool:
        return self.pagina >= self.total_paginas - 1

    def convertir[U](self, funcion: Callable[[T], U]) -> "Pagina[U]":
        """La misma página, con cada elemento transformado.

        Es lo que usa cada capa para pasar de entidad a DTO sin perder los
        metadatos por el camino.
        """
        return Pagina(
            contenido=[funcion(elemento) for elemento in self.contenido],
            pagina=self.pagina,
            tamano=self.tamano,
            total_elementos=self.total_elementos,
            orden=self.orden,
        )


def paginar(
    sesion: Session,
    consulta: Select,
    solicitud: SolicitudDePagina,
    columnas_ordenables: Mapping[str, ColumnElement[Any]],
    desempate: ColumnElement[Any],
    opciones: Sequence[Any] = (),
) -> Pagina:
    """Ejecuta `consulta` devolviendo solo la página pedida, y cuenta el total.

    Son dos consultas: un `COUNT(*)` sobre los mismos filtros -sin orden ni
    carga de relaciones, que no cambian el conteo- y el `SELECT` con `ORDER BY`,
    `LIMIT` y `OFFSET`. El total sale de la base, no de `len()` de todo el
    resultado: paginar trayendo todo para contarlo no sería paginar.

    `columnas_ordenables` es la lista cerrada de campos por los que se puede
    ordenar. El nombre que manda el cliente nunca llega a la consulta: se usa
    solo como llave de ese diccionario, así que no hay forma de inyectar una
    columna -ni una expresión- que el repositorio no haya declarado.

    `desempate` se agrega siempre al final del `ORDER BY`. Sin un orden total,
    dos filas que empatan en el criterio pedido pueden cambiar de lugar entre
    una consulta y la siguiente, y la misma fila aparecería en dos páginas o en
    ninguna.
    """
    total = sesion.scalar(select(func.count()).select_from(consulta.order_by(None).subquery()))

    criterios = [
        columnas_ordenables[orden.campo].desc()
        if orden.descendente
        else columnas_ordenables[orden.campo].asc()
        for orden in solicitud.orden
    ]
    ordenada = (
        consulta.options(*opciones)
        .order_by(*criterios, desempate)
        .limit(solicitud.tamano)
        .offset(solicitud.desplazamiento)
    )
    return Pagina(
        contenido=list(sesion.scalars(ordenada).unique()),
        pagina=solicitud.pagina,
        tamano=solicitud.tamano,
        total_elementos=total or 0,
        orden=solicitud.orden,
    )
