"""Entidad CuentaCorreo: el buzón vinculado del que se leen los comprobantes."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base
from app.data.models.enums import EstadoCuentaCorreo, ProveedorCorreo
from app.data.models.tipos import FechaHoraUTC
from app.data.models.usuario import Usuario

if TYPE_CHECKING:
    from app.data.models.comprobante import Comprobante
    from app.data.models.transferencia_sinpe import TransferenciaSinpe


class CuentaCorreo(Base):
    """Buzón vinculado del que se leen los comprobantes.

    Se separa de `Usuario` porque una persona puede vincular más de un buzón (el
    personal y el del trabajo), porque los tokens caducan y hay que renovarlos
    por su cuenta, y porque desvincular un correo no puede implicar borrar la
    cuenta.

    Los tokens nunca se guardan en claro: `token_acceso_cifrado` y
    `token_refresco_cifrado` pasan por `business.seguridad.cifrado` antes de
    llegar aquí. Esta entidad no sabe cifrar ni descifrar, solo persiste lo que
    el servicio ya cifró.
    """

    __tablename__ = "cuenta_correo"
    __table_args__ = (
        UniqueConstraint("usuario_id", "direccion", name="uq_cuenta_correo_usuario_direccion"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False, index=True)
    proveedor: Mapped[ProveedorCorreo] = mapped_column(Enum(ProveedorCorreo), nullable=False)
    direccion: Mapped[str] = mapped_column(String(180), nullable=False)
    # Text, no String(n): un token cifrado con Fernet no tiene un largo fijo
    # -depende de cuanto mande Microsoft o Google, que puede variar bastante-
    # y SQLite nunca hizo respetar ningun limite aqui. Con PostgreSQL, que si
    # lo exige de verdad, un access token real superaba los 2000 caracteres
    # que tenia esta columna y la vinculacion fallaba con
    # StringDataRightTruncation en el INSERT.
    token_acceso_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_refresco_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    expira_en: Mapped[datetime | None] = mapped_column(FechaHoraUTC, nullable=True)
    ultima_sincronizacion: Mapped[datetime | None] = mapped_column(FechaHoraUTC, nullable=True)
    estado: Mapped[EstadoCuentaCorreo] = mapped_column(
        Enum(EstadoCuentaCorreo), nullable=False, default=EstadoCuentaCorreo.ACTIVA
    )

    usuario: Mapped[Usuario] = relationship(back_populates="cuentas_correo", lazy="select")
    # Con cascada: el comprobante y la transferencia son la cache de lo que se
    # leyo de ESE buzon. Desvincular la cuenta y dejar sus filas huerfanas
    # dejaria gasto que ya no se puede rastrear a ningun correo.
    comprobantes: Mapped[list["Comprobante"]] = relationship(
        back_populates="cuenta_correo", cascade="all, delete-orphan", lazy="select"
    )
    transferencias_sinpe: Mapped[list["TransferenciaSinpe"]] = relationship(
        back_populates="cuenta_correo", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"CuentaCorreo(id={self.id!r}, proveedor={self.proveedor!r}, "
            f"direccion={self.direccion!r})"
        )
