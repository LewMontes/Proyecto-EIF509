"""La paginación en el contrato HTTP: los parámetros de entrada y el sobre de salida.

Toda colección paginada se pide igual y se responde igual:

    GET /api/v1/compras?pagina=0&tamano=20&orden=fecha,desc&orden=total,asc

    {
      "contenido": [ ... ],
      "pagina": 0, "tamano": 20,
      "total_elementos": 137, "total_paginas": 7,
      "primera": true, "ultima": false,
      "orden": ["fecha,desc", "total,asc"]
    }

Es la misma forma que `Pageable` y `Page` de Spring Data: página desde cero,
tamaño, y `orden` como `campo,sentido`, repetible para ordenar por varios.
"""

from collections.abc import Callable, Iterable
from typing import Annotated

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

from app.data.paginacion import (
    TAMANO_MAXIMO,
    TAMANO_POR_DEFECTO,
    Orden,
    Pagina,
    SolicitudDePagina,
)

_SENTIDOS = ("asc", "desc")


class PaginaResponse[T](BaseModel):
    """Una página de una colección, con sus metadatos."""

    contenido: list[T]
    pagina: int = Field(description="Número de esta página. La primera es la 0.")
    tamano: int = Field(description="Cuántos elementos se pidieron por página.")
    total_elementos: int = Field(description="Cuántos elementos hay en total, con los filtros.")
    total_paginas: int
    primera: bool
    ultima: bool
    orden: list[str] = Field(description="El orden aplicado, como `campo,sentido`.")


def respuesta_de_pagina[T, U](pagina: Pagina[T], convertir: Callable[[T], U]) -> PaginaResponse[U]:
    """Arma el sobre de salida, convirtiendo cada elemento a su DTO de respuesta."""
    return PaginaResponse(
        contenido=[convertir(elemento) for elemento in pagina.contenido],
        pagina=pagina.pagina,
        tamano=pagina.tamano,
        total_elementos=pagina.total_elementos,
        total_paginas=pagina.total_paginas,
        primera=pagina.es_primera,
        ultima=pagina.es_ultima,
        orden=[f"{orden.campo},{'desc' if orden.descendente else 'asc'}" for orden in pagina.orden],
    )


def parametros_de_pagina(
    campos_ordenables: Iterable[str], orden_por_defecto: str
) -> Callable[..., SolicitudDePagina]:
    """Fabrica la dependencia que lee `pagina`, `tamano` y `orden` de la URL.

    Cada endpoint la arma con **su** lista de campos ordenables -la misma que
    declara su repositorio-: pedir un orden por un campo que no está en la
    lista es un 400, no una columna que llega a la consulta.
    """
    campos = tuple(campos_ordenables)

    def _leer(
        pagina: Annotated[int, Query(ge=0, description="Número de página, desde 0.")] = 0,
        tamano: Annotated[
            int, Query(ge=1, le=TAMANO_MAXIMO, description="Elementos por página.")
        ] = TAMANO_POR_DEFECTO,
        orden: Annotated[
            list[str] | None,
            Query(
                description=(
                    "`campo,asc` o `campo,desc`. Repetible para ordenar por varios. "
                    f"Campos: {', '.join(campos)}. Por defecto: `{orden_por_defecto}`."
                ),
                examples=[orden_por_defecto],
            ),
        ] = None,
    ) -> SolicitudDePagina:
        criterios = []
        for posicion, texto in enumerate(orden or [orden_por_defecto]):
            campo, _, sentido = texto.partition(",")
            campo, sentido = campo.strip(), (sentido.strip() or "asc").lower()
            if campo not in campos or sentido not in _SENTIDOS:
                # El mismo error que lanzaría Pydantic, para que salga por el
                # mismo manejador y con la misma forma que cualquier otro 400.
                raise RequestValidationError(
                    [
                        {
                            "type": "value_error",
                            "loc": ("query", "orden", posicion),
                            "msg": (
                                f"'{texto}' no es un orden válido. Se espera `campo,asc` o "
                                f"`campo,desc`, con campo en: {', '.join(campos)}."
                            ),
                            "input": texto,
                        }
                    ]
                )
            criterios.append(Orden(campo=campo, descendente=sentido == "desc"))
        return SolicitudDePagina(pagina=pagina, tamano=tamano, orden=tuple(criterios))

    return _leer
