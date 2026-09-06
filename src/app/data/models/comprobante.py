"""Entidad Comprobante: el resultado ya parseado de un mensaje de BAC, guardado.

Antes de esto, cada pantalla que necesitaba el gasto real -resumen, comercios,
presupuestos, reportes- releía y reparseaba la bandeja completa del proveedor
en cada petición: con una bandeja de más de cien mensajes, eso son cien
peticiones HTTP a Microsoft o Google por cada carga de pantalla, cada vez.
Esta tabla es la caché de ese trabajo: el resultado de `parsear_comprobante_bac`
se guarda una sola vez por mensaje, y las pantallas leen de aquí, no del correo.

Lo único que sigue tocando la red es `CuentaCorreoService.sincronizar`, y solo
para los mensajes que todavía no están en esta tabla -`mensaje_id` es la clave
de deduplicación. Sincronizar de nuevo una bandeja ya al día no vuelve a pedir
ningún cuerpo de mensaje, porque no encuentra ningún `mensaje_id` nuevo con qué
hacerlo.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base

if TYPE_CHECKING:
    from app.data.models.compra import Compra
    from app.data.models.cuenta_correo import CuentaCorreo


class Comprobante(Base):
    """Un mensaje de BAC ya leído y parseado, listo para sumar sin volver al correo.

    Es un espejo de `ComprobanteParseado` -el mismo resultado de lectura, ahora
    persistido- no una entidad de negocio nueva: no valida reglas de dominio ni
    se relaciona con `Categoria` o `Comercio`. Esa clasificación se sigue
    resolviendo en memoria con `ComercioService`, ahora sobre estas filas en
    vez de sobre una respuesta del proveedor.
    """

    __tablename__ = "comprobante"
    __table_args__ = (
        UniqueConstraint("cuenta_correo_id", "mensaje_id", name="uq_comprobante_cuenta_mensaje"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cuenta_correo_id: Mapped[int] = mapped_column(
        ForeignKey("cuenta_correo.id"), nullable=False, index=True
    )
    mensaje_id: Mapped[str] = mapped_column(String(300), nullable=False)
    # La `Compra` de negocio real que `ConciliacionService` creó a partir de
    # este comprobante -NULL si la confianza del parseo no alcanzó para
    # conciliar sola (queda en revisión manual). Ver conciliacion_service.py.
    compra_id: Mapped[int | None] = mapped_column(ForeignKey("compra.id"), nullable=True)

    banco: Mapped[str] = mapped_column(String(80), nullable=False)
    comercio: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pais: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Naive a propósito: el parser la extrae del texto del correo sin zona
    # horaria (es la hora local de Costa Rica que BAC escribe en la
    # notificación), y todo lo que la usa -agrupar_por_mes, filtrar_del_periodo-
    # solo mira año y mes. FechaHoraUTC no aplica aquí: es para timestamps del
    # propio sistema (expiración de token, última sincronización), no para un
    # dato de negocio que nunca se compara contra la hora actual.
    fecha: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    marca_tarjeta: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ultimos_cuatro: Mapped[str | None] = mapped_column(String(4), nullable=True)
    autorizacion: Mapped[str | None] = mapped_column(String(60), nullable=True)
    referencia: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tipo_transaccion: Mapped[str | None] = mapped_column(String(40), nullable=True)
    moneda: Mapped[str | None] = mapped_column(String(3), nullable=True)
    monto: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    confianza: Mapped[float] = mapped_column(nullable=False)

    # El tipo de cambio que regía cuando este comprobante se guardó, para poder
    # convertirlo después sin depender de una consulta histórica.
    #
    # El Banco Central sí publica tipos de cambio históricos, pero solo con una
    # suscripción, y su servicio lleva días caído -ni siquiera se puede sacar el
    # token. El respaldo (Hacienda) únicamente publica el del día. Sin guardar
    # nada, convertir una compra de hace tres meses obliga a usar la tasa de
    # hoy, que no es la que pagó.
    #
    # Guardarlo al sincronizar no recupera el pasado -para los comprobantes que
    # ya estaban, estas columnas quedan en NULL y se sigue cayendo a la tasa de
    # hoy- pero deja de perderlo de aquí en adelante. Y como el comprobante
    # normalmente se sincroniza el mismo día o al siguiente de la compra, la
    # tasa guardada es en la práctica la de la compra.
    #
    # `tipo_cambio_fecha` es de qué día es la tasa, que no siempre coincide con
    # `fecha`: al sincronizar una bandeja vieja por primera vez se guarda la
    # tasa de hoy para compras de hace meses. Sin esta columna no habría forma
    # de distinguir una tasa contemporánea de una tardía, y el total parecería
    # más preciso de lo que es.
    tipo_cambio_venta: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    tipo_cambio_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)

    # `cuenta_correo` es la relacion "de quien es este comprobante": el
    # aislamiento entre titulares pasa por aca, porque `Comprobante` no
    # guarda `usuario_id` propio.
    cuenta_correo: Mapped["CuentaCorreo"] = relationship(
        back_populates="comprobantes", lazy="select"
    )
    compra: Mapped[Optional["Compra"]] = relationship(back_populates="comprobantes", lazy="select")

    def __repr__(self) -> str:
        return (
            f"Comprobante(cuenta_correo_id={self.cuenta_correo_id!r}, "
            f"mensaje_id={self.mensaje_id!r}, comercio={self.comercio!r})"
        )
