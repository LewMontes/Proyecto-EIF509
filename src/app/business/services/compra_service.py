"""Lecturas de Compra que no encajan en ConciliacionService (que solo escribe).

Antes de esto, la única forma de "ver" una Compra real desde la API era
indirecta: los campos planos de `Comprobante` (que duplican casi lo mismo) o
los eventos de su bitácora en Mongo -nunca la Compra en sí, ni su
`requiere_revision`, ni con qué método de pago o categoría quedó. Este
servicio es lo que la hace un dato de primera clase: listable, filtrable por
"necesita revisión", y consultable una por una con sus nombres ya resueltos.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.business.errors import DatosInvalidos, RangoInvalido, RecursoNoEncontrado
from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra, OrigenCompra
from app.data.paginacion import Pagina, SolicitudDePagina
from app.data.repositories import especificaciones as esp
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


@dataclass(frozen=True)
class FiltrosDeCompra:
    """Los filtros de negocio de la lista de compras. Todos opcionales y combinables.

    Es lo que el servicio recibe de la presentación; convertir cada uno en una
    especificación y componerlas es trabajo del servicio, no del router.
    """

    desde: date | None = None
    hasta: date | None = None
    categoria_id: int | None = None
    comercio_id: int | None = None
    metodo_pago_id: int | None = None
    estado: EstadoCompra | None = None
    origen: OrigenCompra | None = None
    requiere_revision: bool | None = None
    total_minimo: Decimal | None = None
    total_maximo: Decimal | None = None


class CompraService:
    """Consultas de compras reales ya conciliadas."""

    # Por qué campos se puede ordenar la lista. La presentación lo lee de acá
    # para validar el parámetro `orden` sin conocer al repositorio.
    CAMPOS_ORDENABLES = tuple(CompraRepository.COLUMNAS_ORDENABLES)

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

    def buscar_del_titular(
        self, usuario_id: int, filtros: FiltrosDeCompra, solicitud: SolicitudDePagina
    ) -> Pagina[CompraDetallada]:
        """Una página de las compras del titular que cumplen los filtros.

        Cada filtro es una especificación con nombre de negocio, y la búsqueda
        es su conjunción. **Arranca siempre de `del_titular`**: es la
        verificación de propiedad -el `usuario_id` viene del token, y ningún
        filtro que mande el cliente puede sacar la búsqueda de sus propias
        compras.

        Valida lo que solo el negocio puede validar: un rango cuyo inicio es
        posterior a su fin está bien formado, pero no puede contener nada.
        """
        if filtros.desde and filtros.hasta and filtros.desde > filtros.hasta:
            raise RangoInvalido(
                f"El rango de fechas está invertido: {filtros.desde} es posterior "
                f"a {filtros.hasta}."
            )
        if (
            filtros.total_minimo is not None
            and filtros.total_maximo is not None
            and filtros.total_minimo > filtros.total_maximo
        ):
            raise RangoInvalido("El total mínimo no puede ser mayor que el máximo.")

        especificacion = esp.todas(
            esp.del_titular(usuario_id),
            esp.entre_fechas(filtros.desde, filtros.hasta),
            esp.de_la_categoria(filtros.categoria_id),
            esp.del_comercio(filtros.comercio_id),
            esp.con_metodo_de_pago(filtros.metodo_pago_id),
            esp.en_estado(filtros.estado),
            esp.de_origen(filtros.origen),
            esp.que_requieren_revision(filtros.requiere_revision),
            esp.con_total_entre(filtros.total_minimo, filtros.total_maximo),
        )
        return self.compras.buscar(especificacion, solicitud).convertir(self._detallar)

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
            raise DatosInvalidos(f"El mes {mes} no existe: tiene que estar entre 1 y 12.")
        if categoria_ids is not None and not categoria_ids:
            # Una lista vacía significaría "ninguna categoría", que devuelve
            # siempre vacío: casi seguro es un filtro mal armado, no una
            # pregunta real. `None` es como se pide "todas".
            raise DatosInvalidos("La lista de categorias no puede venir vacia.")
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
