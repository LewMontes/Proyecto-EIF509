"""La cadena de categorización, compartida por los dos procesos del dominio.

Decidir la categoría de un gasto tiene varias fuentes posibles con una
precedencia clara: lo que el titular eligió a mano; si no eligió, las reglas
que él mismo definió, en orden de prioridad ascendente; si ninguna coincide,
la categoría que ese titular le asignó al comercio; y si tampoco hay, ninguna.

Es una **cadena de responsabilidad** de verdad, no un `if` detrás de otro:
cada fuente es un eslabón con la misma interfaz -`FuenteDeCategoria.resolver`-
que resuelve la categoría o devuelve `None` para que decida el siguiente, y
`CadenaDeCategorizacion` las recorre en orden sin saber qué hace cada una. La
precedencia queda expresada por el orden en que se arma la cadena, y agregar
una fuente nueva -una sugerencia global del comercio, por ejemplo- es escribir
una clase y ponerla en la lista, sin reabrir las que ya estaban.

Vive acá porque la necesitan los dos procesos -la conciliación de un
comprobante (`ConciliacionService`) y el registro manual
(`RegistrarCompraService`)- y tienen que decidir igual: que la misma compra
caiga en una categoría distinta según por dónde entró sería un error que
nadie notaría hasta cuadrar un reporte a mano. Cada proceso arma la cadena con
los eslabones que le corresponden: la ingesta no tiene un titular eligiendo,
así que la suya empieza en las reglas.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.data.models.regla_categorizacion import ReglaCategorizacion


class OrigenDeCategoria(StrEnum):
    """Qué eslabón de la cadena resolvió la categoría."""

    TITULAR = "TITULAR"
    REGLA = "REGLA"
    COMERCIO = "COMERCIO"


@dataclass(frozen=True)
class ContextoDeCategorizacion:
    """Lo que un eslabón puede mirar para decidir.

    Es inmutable y es lo único que viaja por la cadena: ningún eslabón conoce
    al servicio que lo llamó ni al eslabón anterior.
    """

    usuario_id: int
    comercio_id: int
    comercio_normalizado: str
    # La categoría que el titular indicó a mano, si indicó alguna. La ingesta
    # por correo nunca la trae: nadie eligió nada todavía.
    categoria_elegida_id: int | None = None


@dataclass(frozen=True)
class CategoriaResuelta:
    """La decisión de un eslabón: qué categoría, y de dónde salió."""

    categoria_id: int
    origen: OrigenDeCategoria
    # La regla que acertó, cuando el origen es `REGLA`: quien llama le sube el
    # contador de aciertos dentro de su propia transacción.
    regla: ReglaCategorizacion | None = None


class FuenteDeCategoria(Protocol):
    """Un eslabón de la cadena.

    Devuelve la categoría si la puede resolver, o `None` para pasarle la
    decisión al siguiente. Nunca lanza una excepción por «no sé»: no saber es
    el caso normal de casi todos los eslabones casi todo el tiempo.
    """

    def resolver(self, contexto: ContextoDeCategorizacion) -> CategoriaResuelta | None: ...


class CategoriaElegidaPorElTitular:
    """Primer eslabón del registro manual: la decisión explícita del titular.

    Va antes que cualquier regla a propósito. Corregir es justamente lo que
    hace aprender al sistema, así que una regla que el titular creó antes no
    puede pisar lo que él decide ahora.
    """

    def resolver(self, contexto: ContextoDeCategorizacion) -> CategoriaResuelta | None:
        if contexto.categoria_elegida_id is None:
            return None
        return CategoriaResuelta(contexto.categoria_elegida_id, OrigenDeCategoria.TITULAR)


class ReglasDelTitular:
    """Las reglas activas del titular, recorridas por prioridad ascendente.

    Recibe una función que trae las reglas y no el repositorio: así el eslabón
    no sabe de dónde salen, y se puede probar con una lista en memoria.

    Las reglas se leen una sola vez por titular y se recuerdan mientras viva
    el eslabón. El registro manual pasa por acá una vez por renglón, y las
    reglas son las mismas para todos los renglones de una compra: consultarlas
    cien veces para una compra de cien renglones no cambiaría ninguna decisión.
    Por eso cada proceso arma una cadena nueva por operación en vez de guardar
    una por servicio.
    """

    def __init__(self, reglas_activas_de: Callable[[int], Iterable[ReglaCategorizacion]]) -> None:
        self._reglas_activas_de = reglas_activas_de
        self._leidas: dict[int, list[ReglaCategorizacion]] = {}

    def resolver(self, contexto: ContextoDeCategorizacion) -> CategoriaResuelta | None:
        if contexto.usuario_id not in self._leidas:
            self._leidas[contexto.usuario_id] = list(self._reglas_activas_de(contexto.usuario_id))
        regla = primera_regla_que_coincide(
            self._leidas[contexto.usuario_id], contexto.comercio_normalizado
        )
        if regla is None:
            return None
        return CategoriaResuelta(regla.categoria_destino_id, OrigenDeCategoria.REGLA, regla)


class SugerenciaDelComercio:
    """Último eslabón: la categoría que este titular le asignó a este comercio.

    Es «corregir crea la regla»: la primera vez que el titular clasifica una
    compra de un comercio, esa categoría queda como sugerida y las siguientes
    compras ahí entran solas.
    """

    def __init__(self, categoria_sugerida_para: Callable[[int, int], int | None]) -> None:
        self._categoria_sugerida_para = categoria_sugerida_para

    def resolver(self, contexto: ContextoDeCategorizacion) -> CategoriaResuelta | None:
        categoria_id = self._categoria_sugerida_para(contexto.usuario_id, contexto.comercio_id)
        if categoria_id is None:
            return None
        return CategoriaResuelta(categoria_id, OrigenDeCategoria.COMERCIO)


class CadenaDeCategorizacion:
    """Recorre las fuentes en orden y se queda con la primera que resuelve."""

    def __init__(self, fuentes: Sequence[FuenteDeCategoria]) -> None:
        self._fuentes = tuple(fuentes)

    def resolver(self, contexto: ContextoDeCategorizacion) -> CategoriaResuelta | None:
        """La categoría según el primer eslabón que la sepa, o `None` si ninguno la sabe.

        `None` no es un error de la cadena: qué hacer con un gasto que nadie
        supo clasificar lo decide cada proceso -la ingesta lo deja para
        revisión, el registro manual lo rechaza.
        """
        for fuente in self._fuentes:
            resuelta = fuente.resolver(contexto)
            if resuelta is not None:
                return resuelta
        return None


def primera_regla_que_coincide(
    reglas: Iterable[ReglaCategorizacion], comercio_normalizado: str
) -> ReglaCategorizacion | None:
    """La primera regla cuyo patrón está contenido en el nombre normalizado del comercio.

    **Gana la primera que coincide**, no la más específica: es lo que permite
    poner una excepción (`WALMART EXPRESS` → Conveniencia) antes que la
    general (`WALMART` → Supermercado) simplemente dándole menor prioridad.
    Por eso quien llama tiene que pasar las reglas ya ordenadas por prioridad
    ascendente -`ReglaCategorizacionRepository.listar_activas_ordenadas` lo
    hace- y por eso `ReglaCategorizacionService` rechaza dos reglas del mismo
    titular con la misma prioridad: con un empate, cuál gana dependería del
    orden en que la base devolviera las filas.
    """
    for regla in reglas:
        if regla.patron.upper() in comercio_normalizado:
            return regla
    return None
