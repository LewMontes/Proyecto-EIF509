"""Consultas de LineaCompra."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models.compra import Compra
from app.data.models.linea_compra import LineaCompra
from app.data.repositories.base_repository import BaseRepository


class LineaCompraRepository(BaseRepository[LineaCompra]):
    """Acceso a los renglones de una compra."""

    def __init__(self, sesion: Session) -> None:
        super().__init__(sesion, LineaCompra)

    def listar_de_compra(self, compra_id: int) -> list[LineaCompra]:
        return list(
            self.sesion.scalars(select(LineaCompra).where(LineaCompra.compra_id == compra_id))
        )

    def listar_sin_categoria_de_comercio(
        self, usuario_id: int, comercio_id: int
    ) -> list[tuple[LineaCompra, Compra]]:
        """Renglones sin categoría de compras de este comercio y titular.

        Es lo que usa `ConciliacionService.recategorizar_compras_de_comercio`
        para que asignarle categoría a un comercio no deje "huérfanas" las
        compras que ya se conciliaron antes de esa asignación -"corregir crea
        la regla" también corrige lo que ya pasó, no solo lo que viene.
        """
        filas = self.sesion.execute(
            select(LineaCompra, Compra)
            .join(Compra, LineaCompra.compra_id == Compra.id)
            .where(
                Compra.usuario_id == usuario_id,
                Compra.comercio_id == comercio_id,
                LineaCompra.categoria_id.is_(None),
            )
        )
        return [(linea, compra) for linea, compra in filas]
