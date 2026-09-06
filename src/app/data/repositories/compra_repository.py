"""Consultas de Compra."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, extract, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.data.models.categoria import Categoria
from app.data.models.compra import Compra
from app.data.models.enums import EstadoCompra
from app.data.models.linea_compra import LineaCompra
from app.data.repositories.base_repository import BaseRepository


@dataclass(frozen=True)
class GastoDeCategoria:
    """Cuánto gastó un titular en una categoría durante un periodo."""

    categoria_id: int | None
    categoria_nombre: str
    total: Decimal
    cantidad_de_renglones: int


class CompraRepository(BaseRepository[Compra]):
    """Acceso a las compras de un titular."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, Compra)

    def obtener_de_usuario(self, identificador: int, usuario_id: int) -> Compra | None:
        """La compra, solo si pertenece al titular. Sin cargar nada más.

        Es la consulta de "¿esto es tuyo?" -la usan la bitácora y la anulación,
        que solo necesitan saber que la compra existe en esta cuenta. Cargarle
        el comercio y los renglones sería traer datos que nadie va a leer; para
        eso está `obtener_detallada_de_usuario`.
        """
        return self.sesion.scalars(
            select(Compra).where(Compra.id == identificador, Compra.usuario_id == usuario_id)
        ).first()

    def obtener_detallada_de_usuario(self, identificador: int, usuario_id: int) -> Compra | None:
        """La compra con su comercio, método de pago, renglones y categorías ya cargados."""
        return self.sesion.scalars(
            select(Compra)
            .options(*self._relaciones_del_detalle())
            .where(Compra.id == identificador, Compra.usuario_id == usuario_id)
        ).first()

    def listar_de_usuario(
        self, usuario_id: int, requiere_revision: bool | None = None, limite: int = 50
    ) -> list[Compra]:
        """Las compras del titular, más recientes primero, listas para detallar.

        `requiere_revision` filtra por esa columna cuando no es `None` -es lo
        que arma la lista de "compras que necesitan revisión" sin traer todo
        el historial para filtrarlo en Python.

        Las relaciones vienen cargadas por adelantado (`_relaciones_del_detalle`)
        porque quien llama a esta consulta -la pantalla de Compras- las va a
        leer todas, siempre. Sin eso, listar 50 compras costaba 201 consultas;
        con eso, 2. Ver docs/persistencia.md, sección 5.
        """
        consulta = select(Compra).options(*self._relaciones_del_detalle())
        consulta = consulta.where(Compra.usuario_id == usuario_id)
        if requiere_revision is not None:
            consulta = consulta.where(Compra.requiere_revision.is_(requiere_revision))
        consulta = consulta.order_by(Compra.fecha.desc(), Compra.id.desc()).limit(limite)
        return list(self.sesion.scalars(consulta))

    def gasto_por_categoria(
        self,
        usuario_id: int,
        anio: int,
        mes: int,
        categoria_ids: list[int] | None = None,
        metodo_pago_id: int | None = None,
        incluir_sin_categoria: bool = True,
    ) -> list[GastoDeCategoria]:
        """Cuánto gastó el titular en cada categoría durante un mes, de mayor a menor.

        Es la única consulta agregada del sistema: la base suma y agrupa, en vez
        de traer los renglones del mes para sumarlos en Python. Sobre un
        historial de un año son cientos de filas que nunca salen de PostgreSQL.

        **Por qué suma renglones y no compras.** La categoría vive en
        `LineaCompra`, no en `Compra` -una compra desglosada a mano puede tener
        renglones de categorías distintas. Sumar `Compra.total` agrupando por
        categoría contaría esa compra completa en cada una de sus categorías.

        **Por qué multiplica por el tipo de cambio.** `LineaCompra.subtotal`
        está en la moneda de su compra, así que sumar renglones en dólares y en
        colones daría un número que no significa nada. `tipo_cambio_aplicado`
        es el que regía el día de la compra y quedó congelado en ella (ver
        `Compra`), así que el total sale en moneda base con la tasa de
        entonces, no con la de hoy.

        Los tres filtros de abajo son opcionales y se combinan: es la parte
        dinámica, el equivalente de armar una *Specification*. `None` en
        `categoria_ids` o `metodo_pago_id` significa "no filtrar por eso", no
        "filtrar por nulo".
        """
        monto = LineaCompra.subtotal * Compra.tipo_cambio_aplicado
        consulta = (
            select(
                LineaCompra.categoria_id,
                func.coalesce(Categoria.nombre, "Sin categoria").label("categoria_nombre"),
                func.sum(monto).label("total"),
                func.count(LineaCompra.id).label("cantidad"),
            )
            .join(Compra, LineaCompra.compra_id == Compra.id)
            .outerjoin(Categoria, LineaCompra.categoria_id == Categoria.id)
        )
        consulta = self._del_periodo(consulta, usuario_id, anio, mes)

        if categoria_ids is not None:
            consulta = consulta.where(LineaCompra.categoria_id.in_(categoria_ids))
        if metodo_pago_id is not None:
            consulta = consulta.where(Compra.metodo_pago_id == metodo_pago_id)
        if not incluir_sin_categoria:
            consulta = consulta.where(LineaCompra.categoria_id.is_not(None))

        consulta = consulta.group_by(LineaCompra.categoria_id, Categoria.nombre).order_by(
            func.sum(monto).desc()
        )
        return [
            GastoDeCategoria(
                categoria_id=fila.categoria_id,
                categoria_nombre=fila.categoria_nombre,
                total=Decimal(fila.total).quantize(Decimal("0.01")),
                cantidad_de_renglones=fila.cantidad,
            )
            for fila in self.sesion.execute(consulta)
        ]

    @staticmethod
    def _del_periodo(consulta: Select, usuario_id: int, anio: int, mes: int) -> Select:
        """Acota a las compras del titular de ese año y mes que sí cuentan como gasto.

        `extract` en vez de un rango de fechas porque el mes es el periodo
        natural del dominio -el presupuesto es mensual- y así la consulta dice
        lo que significa sin que quien la lea tenga que calcular el último día
        del mes.

        Las compras anuladas quedan fuera: siguen en la base como historial,
        pero por definición no son gasto (`ConciliacionService.anular`
        devuelve su monto al presupuesto).
        """
        return consulta.where(
            Compra.usuario_id == usuario_id,
            extract("year", Compra.fecha) == anio,
            extract("month", Compra.fecha) == mes,
            Compra.estado != EstadoCompra.ANULADA,
        )

    @staticmethod
    def _relaciones_del_detalle():
        """Lo que hace falta para armar un `CompraDetallada` sin volver a la base.

        `joinedload` para los `*-a-uno` (comercio y método de pago): son un
        `LEFT JOIN` en la misma consulta, sin costo de filas extra porque cada
        compra tiene a lo sumo uno de cada.

        `selectinload` para los renglones, que son una colección. Con
        `joinedload` sobre una colección, el `LIMIT 50` de la consulta se
        aplicaría a las filas del producto cartesiano y no a las compras: una
        compra con tres renglones se comería tres lugares de la página.
        `selectinload` los trae aparte, con un solo `WHERE compra_id IN (...)`.
        """
        return (
            joinedload(Compra.comercio),
            joinedload(Compra.metodo_pago),
            selectinload(Compra.lineas).joinedload(LineaCompra.categoria),
        )
