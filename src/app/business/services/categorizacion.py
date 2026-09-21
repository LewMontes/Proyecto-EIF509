"""La cadena de categorización, compartida por los dos procesos del dominio.

Decidir la categoría de un gasto tiene varias fuentes posibles con una
precedencia clara: primero las reglas que el titular definió, en orden de
prioridad ascendente; si ninguna coincide, la categoría que ese titular le
asignó al comercio; si tampoco hay, ninguna.

El primer eslabón vive acá porque lo necesitan los dos procesos -la
conciliación de un comprobante (`ConciliacionService`) y el registro manual
(`RegistrarCompraService`)- y tienen que decidir igual: que la misma compra
caiga en una categoría distinta según por dónde entró sería un error que
nadie notaría hasta cuadrar un reporte a mano.

Es una función pura: recibe las reglas ya leídas y devuelve la que gana, sin
tocar la base. Así cada servicio decide cuándo consultarlas -uno lo hace una
vez por comprobante, el otro una vez por compra y reutiliza la lista para
todos sus renglones- sin que esta decisión dependa de eso.
"""

from collections.abc import Iterable

from app.data.models.regla_categorizacion import ReglaCategorizacion


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

    `None` si ninguna coincide: la decisión pasa al siguiente eslabón de la
    cadena, que resuelve quien llama.
    """
    for regla in reglas:
        if regla.patron.upper() in comercio_normalizado:
            return regla
    return None
