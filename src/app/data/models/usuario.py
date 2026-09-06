"""Entidad Usuario: la raiz de aislamiento del sistema."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.models.base import Base
from app.data.models.enums import Moneda
from app.data.models.tipos import FechaHoraUTC

if TYPE_CHECKING:
    from app.data.models.categoria import Categoria
    from app.data.models.comercio_categoria_sugerida import ComercioCategoriaSugerida
    from app.data.models.compra import Compra
    from app.data.models.cuenta_correo import CuentaCorreo
    from app.data.models.metodo_pago import MetodoPago
    from app.data.models.presupuesto import Presupuesto
    from app.data.models.regla_categorizacion import ReglaCategorizacion


class Usuario(Base):
    """Persona duena de su cuenta y de sus datos.

    Toda consulta del sistema se filtra por usuario: es lo que permite que
    cualquiera se registre sin ver los datos de nadie mas.
    """

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(120), nullable=False)
    correo: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    # Nula para una cuenta que solo inicia sesión con Google -no tiene
    # contraseña propia que hashear. `AuthService.iniciar_sesion` (con
    # correo y contraseña) rechaza cualquier fila con este campo en None
    # antes de intentar verificar nada.
    contrasena_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # El identificador estable de la cuenta de Google ("sub"), si el titular
    # vinculó "Iniciar sesión con Google". Único: dos titulares nunca pueden
    # compartir la misma cuenta de Google como método de acceso.
    google_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    moneda_preferida: Mapped[Moneda] = mapped_column(
        Enum(Moneda), nullable=False, default=Moneda.CRC
    )
    # Apagado por default: buscar "sinpe" en cada buzón activo es una
    # petición real por cuenta antes de poder parsear nada, y no todo
    # titular quiere pagar ese costo en cada carga de la pantalla SINPE.
    # `CuentaCorreoService.transferencias_sinpe_de_usuario` respeta esta
    # bandera antes de tocar la red.
    leer_transferencias_sinpe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        FechaHoraUTC, nullable=False, default=lambda: datetime.now(UTC)
    )

    # Todo lo que cuelga del titular se carga perezosamente (`lazy="select"`,
    # el default de SQLAlchemy, escrito explicito para que se lea como una
    # decision y no como una omision). El criterio, para todas las relaciones
    # del modelo: nunca cargar de mas por el solo hecho de navegar al padre.
    #
    # Aca es donde mas se nota. `Usuario` es la raiz de aislamiento del
    # sistema: se carga en cada peticion autenticada solo para validar el
    # token. Con carga ansiosa, ese `SELECT` arrastraria el historial completo
    # del titular -sus compras, sus comprobantes, sus presupuestos- en cada
    # llamada a cualquier endpoint.
    #
    # La carga ansiosa se decide por consulta, donde se sabe que el dato se va
    # a usar (ver `CompraRepository.listar_de_usuario`), nunca en el mapeo.
    categorias: Mapped[list["Categoria"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )
    cuentas_correo: Mapped[list["CuentaCorreo"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )
    metodos_pago: Mapped[list["MetodoPago"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )
    compras: Mapped[list["Compra"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )
    presupuestos: Mapped[list["Presupuesto"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )
    reglas_categorizacion: Mapped[list["ReglaCategorizacion"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )
    categorias_sugeridas: Mapped[list["ComercioCategoriaSugerida"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"Usuario(id={self.id!r}, correo={self.correo!r})"
