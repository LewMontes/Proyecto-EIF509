"""Reglas de negocio de los presupuestos por categoría."""

from dataclasses import dataclass
from decimal import Decimal

from app.business.errors import (
    CategoriaNoEsHoja,
    DatosInvalidos,
    PresupuestoYaExiste,
    RecursoNoEncontrado,
    UsuarioInactivo,
)
from app.data.models.enums import EstadoPresupuesto, Moneda
from app.data.models.presupuesto import Presupuesto
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.usuario_repository import UsuarioRepository

MES_MINIMO = 1
MES_MAXIMO = 12
ANIO_MINIMO = 2000
ANIO_MAXIMO = 2100
UMBRAL_MINIMO = 1
UMBRAL_MAXIMO = 100


@dataclass(frozen=True)
class EstadoDePresupuesto:
    """El límite de un presupuesto junto con su consumo real del período."""

    presupuesto_id: int
    categoria_id: int
    categoria_nombre: str
    anio: int
    mes: int
    moneda: str
    monto_limite: Decimal
    monto_consumido: Decimal
    umbral_alerta: int
    porcentaje_usado: float
    estado: EstadoPresupuesto


class PresupuestoService:
    """Aplica las reglas del dominio sobre los presupuestos de un titular.

    No lee correo ni sabe qué es un comercio: `calcular_estados` solo lee el
    límite y el consumo ya acumulado de cada presupuesto -acumularlo es
    trabajo de `ConciliacionService`, dentro de la transacción que registra
    cada compra real.
    """

    def __init__(
        self,
        presupuesto_repository: PresupuestoRepository,
        categoria_repository: CategoriaRepository,
        usuario_repository: UsuarioRepository,
    ) -> None:
        self.presupuestos = presupuesto_repository
        self.categorias = categoria_repository
        self.usuarios = usuario_repository

    def crear_o_actualizar(
        self,
        usuario_id: int,
        categoria_id: int,
        anio: int,
        mes: int,
        moneda: Moneda,
        monto_limite: Decimal,
        umbral_alerta: int = 80,
    ) -> Presupuesto:
        """Crea el presupuesto del período, o corrige el límite si ya existía uno.

        No hay "un presupuesto por mes que se duplica sin querer": pedir el
        mismo (categoría, año, mes) dos veces actualiza el límite en vez de
        crear una segunda fila -mismo criterio que vincular un correo dos
        veces en `CuentaCorreoService.vincular`.
        """
        self._asegurar_usuario_activo(usuario_id)

        if not (ANIO_MINIMO <= anio <= ANIO_MAXIMO):
            raise DatosInvalidos(f"El año debe estar entre {ANIO_MINIMO} y {ANIO_MAXIMO}.")
        if not (MES_MINIMO <= mes <= MES_MAXIMO):
            raise DatosInvalidos(f"El mes debe estar entre {MES_MINIMO} y {MES_MAXIMO}.")
        if monto_limite <= 0:
            raise DatosInvalidos("El límite del presupuesto debe ser mayor que cero.")
        if not (UMBRAL_MINIMO <= umbral_alerta <= UMBRAL_MAXIMO):
            raise DatosInvalidos(
                f"El umbral de alerta debe ser un porcentaje entre "
                f"{UMBRAL_MINIMO} y {UMBRAL_MAXIMO}."
            )

        categoria = self.categorias.obtener_de_usuario(categoria_id, usuario_id)
        if categoria is None:
            raise RecursoNoEncontrado(f"La categoría {categoria_id} no existe en esta cuenta.")
        if not categoria.es_hoja:
            raise CategoriaNoEsHoja(
                f"'{categoria.nombre}' es una categoría padre; el presupuesto se pone en la "
                "hoja que recibe el gasto, no en la que solo totaliza."
            )

        presupuesto = self.presupuestos.buscar(usuario_id, categoria_id, anio, mes)
        if presupuesto is None:
            presupuesto = Presupuesto(
                usuario_id=usuario_id, categoria_id=categoria_id, anio=anio, mes=mes
            )
        presupuesto.moneda = moneda
        presupuesto.monto_limite = monto_limite
        presupuesto.umbral_alerta = umbral_alerta

        self.presupuestos.agregar(presupuesto)
        self.presupuestos.sesion.commit()
        return presupuesto

    def crear(
        self,
        usuario_id: int,
        categoria_id: int,
        anio: int,
        mes: int,
        moneda: Moneda,
        monto_limite: Decimal,
        umbral_alerta: int = 80,
    ) -> Presupuesto:
        """Crea el presupuesto del período; si ya hay uno, lo rechaza.

        Es la creación estricta que usa la API: un `POST` que a veces crea y a
        veces modifica no puede responder siempre `201`. Corregir un
        presupuesto que ya existe es `actualizar`.
        """
        self._asegurar_usuario_activo(usuario_id)
        if self.presupuestos.buscar(usuario_id, categoria_id, anio, mes) is not None:
            raise PresupuestoYaExiste(
                f"Ya hay un presupuesto para esa categoría en {anio}-{mes:02d}."
            )
        return self.crear_o_actualizar(
            usuario_id, categoria_id, anio, mes, moneda, monto_limite, umbral_alerta
        )

    def obtener(self, usuario_id: int, presupuesto_id: int) -> Presupuesto:
        """El presupuesto, solo si pertenece al titular que lo pide."""
        return self._obtener_del_titular(usuario_id, presupuesto_id)

    def actualizar(
        self, usuario_id: int, presupuesto_id: int, monto_limite: Decimal, umbral_alerta: int
    ) -> Presupuesto:
        """Corrige el límite y el umbral de un presupuesto del titular.

        No cambia la categoría ni el período: eso sería otro presupuesto. Y no
        toca `monto_consumido`, que solo se mueve con las compras.
        """
        presupuesto = self._obtener_del_titular(usuario_id, presupuesto_id)
        if monto_limite <= 0:
            raise DatosInvalidos("El límite del presupuesto debe ser mayor que cero.")
        if not (UMBRAL_MINIMO <= umbral_alerta <= UMBRAL_MAXIMO):
            raise DatosInvalidos(
                f"El umbral de alerta debe ser un porcentaje entre "
                f"{UMBRAL_MINIMO} y {UMBRAL_MAXIMO}."
            )
        presupuesto.monto_limite = monto_limite
        presupuesto.umbral_alerta = umbral_alerta
        self.presupuestos.sesion.commit()
        return presupuesto

    def listar_del_periodo(self, usuario_id: int, anio: int, mes: int) -> list[Presupuesto]:
        self._asegurar_usuario_activo(usuario_id)
        return self.presupuestos.listar_del_periodo(usuario_id, anio, mes)

    def eliminar(self, usuario_id: int, presupuesto_id: int) -> None:
        presupuesto = self._obtener_del_titular(usuario_id, presupuesto_id)
        self.presupuestos.sesion.delete(presupuesto)
        self.presupuestos.sesion.commit()

    def calcular_estados(self, usuario_id: int, anio: int, mes: int) -> list[EstadoDePresupuesto]:
        """El estado de cada presupuesto del período, con su consumo ya acumulado.

        `Presupuesto.monto_consumido` lo acumula `ConciliacionService` dentro
        de la misma transacción que registra cada compra real -esta función
        ya no recalcula nada a partir de los comprobantes: solo lee el
        límite y el consumo ya guardados y calcula el porcentaje y el
        estado. Antes de que existiera esa conciliación, esto combinaba el
        límite con `ComercioService.clasificar_comprobantes` en cada
        llamada; ahora esa cuenta vive en la fila.
        """
        presupuestos = self.listar_del_periodo(usuario_id, anio, mes)
        if not presupuestos:
            return []

        estados = []
        for presupuesto in presupuestos:
            categoria = self.categorias.obtener_por_id(presupuesto.categoria_id)
            if categoria is None:
                continue
            porcentaje, estado = self.calcular_estado(
                presupuesto.monto_consumido, presupuesto.monto_limite, presupuesto.umbral_alerta
            )
            estados.append(
                EstadoDePresupuesto(
                    presupuesto_id=presupuesto.id,
                    categoria_id=presupuesto.categoria_id,
                    categoria_nombre=categoria.nombre,
                    anio=presupuesto.anio,
                    mes=presupuesto.mes,
                    moneda=presupuesto.moneda.value,
                    monto_limite=presupuesto.monto_limite,
                    monto_consumido=presupuesto.monto_consumido,
                    umbral_alerta=presupuesto.umbral_alerta,
                    porcentaje_usado=porcentaje,
                    estado=estado,
                )
            )
        estados.sort(key=lambda e: e.porcentaje_usado, reverse=True)
        return estados

    @staticmethod
    def calcular_estado(
        monto_consumido: Decimal, monto_limite: Decimal, umbral_alerta: int
    ) -> tuple[float, EstadoPresupuesto]:
        """El porcentaje usado y el estado resultante. Función pura, sin tocar la base."""
        porcentaje = float(monto_consumido / monto_limite * 100) if monto_limite else 0.0
        if porcentaje > 100:
            return porcentaje, EstadoPresupuesto.EXCEDIDO
        if porcentaje >= umbral_alerta:
            return porcentaje, EstadoPresupuesto.CERCA_DEL_LIMITE
        return porcentaje, EstadoPresupuesto.EN_RANGO

    def _obtener_del_titular(self, usuario_id: int, presupuesto_id: int) -> Presupuesto:
        self._asegurar_usuario_activo(usuario_id)
        presupuesto = self.presupuestos.obtener_de_usuario(presupuesto_id, usuario_id)
        if presupuesto is None:
            raise RecursoNoEncontrado(f"El presupuesto {presupuesto_id} no existe en esta cuenta.")
        return presupuesto

    def _asegurar_usuario_activo(self, usuario_id: int) -> None:
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        if not usuario.activo:
            raise UsuarioInactivo(f"El usuario {usuario_id} esta desactivado.")
