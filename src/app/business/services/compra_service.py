"""Lecturas de Compra que no encajan en ConciliacionService (que solo escribe).

Antes de esto, la única forma de "ver" una Compra real desde la API era
indirecta: los campos planos de `Comprobante` (que duplican casi lo mismo) o
los eventos de su bitácora en Mongo -nunca la Compra en sí, ni su
`requiere_revision`, ni con qué método de pago o categoría quedó. Este
servicio es lo que la hace un dato de primera clase: listable, filtrable por
"necesita revisión", y consultable una por una con sus nombres ya resueltos.
"""

from dataclasses import dataclass

from app.business.errors import RecursoNoEncontrado, ValidacionFallida
from app.data.models.compra import Compra
from app.data.repositories.compra_repository import CompraRepository, GastoDeCategoria


@dataclass(frozen=True)
class CompraDetallada:
    """Una Compra junto con los nombres de lo que hoy solo tiene como ids sueltos.

    La categoría sale de su primera línea -toda compra ingerida por correo
    nace con una sola (ver `LineaCompra`)- así que "la categoría de la
    compra" todavía es una simplificación honesta, no una mentira: el día
    que exista desglose manual en varias líneas, esto deja de alcanzar.
    """

    compra: Compra
    comercio_nombre: str
    metodo_pago_alias: str | None
    categoria_id: int | None
    categoria_nombre: str | None


class CompraService:
    """Consultas de compras reales ya conciliadas."""

    def __init__(self, compra_repository: CompraRepository) -> None:
        # Un solo repositorio, no seis. Antes hacían falta los de comercio,
        # método de pago, línea, categoría y usuario porque `_detallar`
        # resolvía cada id a mano, con su propia consulta. Ahora esos nombres
        # llegan por las relaciones que carga `CompraRepository`, y el
        # servicio solo tiene que leerlas.
        self.compras = compra_repository

    def obtener_del_titular(self, usuario_id: int, compra_id: int) -> Compra:
        """La compra, solo si pertenece al titular indicado.

        Es la validación que impide que un titular vea la bitácora de la
        compra de otra persona pasando un id ajeno -Mongo, a diferencia de
        PostgreSQL, no tiene ninguna noción de "de quién es esto" propia.
        """
        compra = self.compras.obtener_de_usuario(compra_id, usuario_id)
        if compra is None:
            raise RecursoNoEncontrado(f"La compra {compra_id} no existe en esta cuenta.")
        return compra

    def listar_del_titular(
        self, usuario_id: int, requiere_revision: bool | None = None, limite: int = 50
    ) -> list[CompraDetallada]:
        """Las compras reales del titular, más recientes primero.

        `requiere_revision=True` filtra solo las que quedaron sin método de
        pago o sin categoría al conciliar -la lista que de verdad hace falta
        para que esa marca deje de ser invisible. `None` trae todas.
        """
        compras = self.compras.listar_de_usuario(usuario_id, requiere_revision, limite)
        return [self._detallar(compra) for compra in compras]

    def obtener_detalle_del_titular(self, usuario_id: int, compra_id: int) -> CompraDetallada:
        compra = self.compras.obtener_detallada_de_usuario(compra_id, usuario_id)
        if compra is None:
            raise RecursoNoEncontrado(f"La compra {compra_id} no existe en esta cuenta.")
        return self._detallar(compra)

    def gasto_por_categoria_del_titular(
        self,
        usuario_id: int,
        anio: int,
        mes: int,
        categoria_ids: list[int] | None = None,
        metodo_pago_id: int | None = None,
        incluir_sin_categoria: bool = True,
    ) -> list[GastoDeCategoria]:
        """En qué se le fue el mes al titular, de mayor a menor.

        Los filtros opcionales sirven para responder preguntas más finas sobre
        el mismo periodo -"solo lo de la tarjeta de crédito", "solo estas tres
        categorías"- sin que cada una necesite su propia consulta.
        """
        if not 1 <= mes <= 12:
            raise ValidacionFallida(f"El mes {mes} no existe: tiene que estar entre 1 y 12.")
        if categoria_ids is not None and not categoria_ids:
            # Una lista vacía significaría "ninguna categoría", que devuelve
            # siempre vacío: casi seguro es un filtro mal armado, no una
            # pregunta real. `None` es como se pide "todas".
            raise ValidacionFallida("La lista de categorias no puede venir vacia.")
        return self.compras.gasto_por_categoria(
            usuario_id, anio, mes, categoria_ids, metodo_pago_id, incluir_sin_categoria
        )

    def _detallar(self, compra: Compra) -> CompraDetallada:
        """Arma el detalle leyendo las relaciones, sin volver a la base.

        Antes esto resolvía a mano cada id -una consulta por el comercio, otra
        por el método de pago, otra por los renglones y otra por la categoría-
        y como se llama una vez por compra, listar 50 costaba 201 consultas.
        Ahora las relaciones ya vienen cargadas por la consulta que trajo la
        compra (`CompraRepository._relaciones_del_detalle`), así que esto es
        solo acceso a atributos. Ver docs/persistencia.md, sección 5.
        """
        # Una compra ingerida por correo siempre nace con una sola línea -ver
        # el docstring de CompraDetallada.
        primera_linea = compra.lineas[0] if compra.lineas else None
        categoria = primera_linea.categoria if primera_linea else None
        return CompraDetallada(
            compra=compra,
            comercio_nombre=compra.comercio.nombre if compra.comercio else "Comercio eliminado",
            metodo_pago_alias=compra.metodo_pago.alias if compra.metodo_pago else None,
            categoria_id=primera_linea.categoria_id if primera_linea else None,
            categoria_nombre=categoria.nombre if categoria else None,
        )
