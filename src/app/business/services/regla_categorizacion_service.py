"""Reglas de negocio de las reglas de categorización de un titular.

Hasta acá, `ReglaCategorizacion` existía solo como modelo, repositorio y
evaluación dentro de `ConciliacionService._categorizar` -ningún endpoint ni
pantalla permitía crear una de verdad, así que el motor siempre caía al
mecanismo viejo (`ComercioCategoriaSugerida`). Este servicio es lo que le da
un dueño real: el titular la crea a mano acá, y de ahí en adelante
`ConciliacionService` la evalúa antes que la sugerencia del comercio.
"""

from dataclasses import dataclass

from app.business.errors import (
    CampoDeReglaNoSoportado,
    CategoriaInactiva,
    CategoriaNoEsHoja,
    DatosInvalidos,
    NombreDuplicado,
    PrioridadDuplicada,
    RecursoNoEncontrado,
    UsuarioInactivo,
)
from app.data.models.enums import CampoRegla
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.usuario_repository import UsuarioRepository

LARGO_MAXIMO_NOMBRE = 80
LARGO_MAXIMO_PATRON = 200

# El motor de categorización (`ConciliacionService._categorizar`) solo evalúa
# contra el nombre normalizado del comercio -es lo único que existe en el
# momento de conciliar un comprobante de correo. `DESCRIPCION_COMPRA` y
# `DESCRIPCION_LINEA` están en el enum porque el dominio los contempla, pero
# hoy siempre valdrían lo mismo que el nombre del comercio (no hay desglose
# manual de una compra todavía -ver LineaCompra), así que ofrecerlos como
# opción real sería prometer una distinción que no existe. Se reactivan el
# día que haya captura manual o desglose de líneas.
CAMPOS_SOPORTADOS = (CampoRegla.COMERCIO_NORMALIZADO,)


@dataclass(frozen=True)
class CrearReglaComando:
    """Orden que recibe el negocio para crear una regla de categorización."""

    usuario_id: int
    nombre: str
    patron: str
    categoria_destino_id: int
    campo: CampoRegla = CampoRegla.COMERCIO_NORMALIZADO
    prioridad: int | None = None


class ReglaCategorizacionService:
    """Aplica las reglas del dominio sobre las reglas de categorización de un titular."""

    def __init__(
        self,
        regla_repository: ReglaCategorizacionRepository,
        categoria_repository: CategoriaRepository,
        usuario_repository: UsuarioRepository,
    ) -> None:
        self.reglas = regla_repository
        self.categorias = categoria_repository
        self.usuarios = usuario_repository

    def crear(self, comando: CrearReglaComando) -> ReglaCategorizacion:
        """Crea una regla de categorización.

        Reglas que aplica:
        - El nombre no puede venir vacío ni repetirse dentro de la cuenta.
        - El patrón no puede venir vacío -una regla que coincide con
          cualquier cosa se comería a las que vienen después en prioridad.
        - `campo` solo acepta `COMERCIO_NORMALIZADO` por ahora -ver
          `CAMPOS_SOPORTADOS`.
        - La categoría destino tiene que ser del titular, hoja y activa: no
          tiene sentido categorizar contra una categoría con subcategorías
          propias, ni contra una que el titular ya desactivó.
        - Sin prioridad explícita, se usa la próxima libre -al final de la
          lista, para no desplazar sin querer una regla que ya existía.
        - Con prioridad explícita, no puede repetir la de otra regla de este
          titular -el motor sería no determinista si dos reglas empataran.
        """
        nombre = comando.nombre.strip()
        if not nombre:
            raise DatosInvalidos("El nombre de la regla no puede venir vacío.")
        if len(nombre) > LARGO_MAXIMO_NOMBRE:
            raise DatosInvalidos(f"El nombre no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres.")

        patron = comando.patron.strip()
        if not patron:
            raise DatosInvalidos("El patrón no puede venir vacío.")
        if len(patron) > LARGO_MAXIMO_PATRON:
            raise DatosInvalidos(f"El patrón no puede pasar de {LARGO_MAXIMO_PATRON} caracteres.")

        if comando.campo not in CAMPOS_SOPORTADOS:
            raise CampoDeReglaNoSoportado(
                f"El campo {comando.campo.value} todavía no está soportado -hoy toda regla "
                "evalúa contra el nombre del comercio."
            )

        self._asegurar_usuario_activo(comando.usuario_id)

        if self.reglas.buscar_por_nombre(comando.usuario_id, nombre) is not None:
            raise NombreDuplicado(f"Ya existe una regla llamada '{nombre}'.")

        categoria = self.categorias.obtener_de_usuario(
            comando.categoria_destino_id, comando.usuario_id
        )
        if categoria is None:
            raise RecursoNoEncontrado(
                f"La categoría {comando.categoria_destino_id} no existe en esta cuenta."
            )
        if not categoria.es_hoja:
            raise CategoriaNoEsHoja("La categoría destino tiene que ser una hoja, no un grupo.")
        if not categoria.activa:
            raise CategoriaInactiva("La categoría destino está desactivada.")

        prioridad = comando.prioridad
        if prioridad is None:
            prioridad = self.reglas.prioridad_siguiente(comando.usuario_id)
        elif prioridad < 1:
            raise DatosInvalidos("La prioridad tiene que ser un número positivo.")
        elif self.reglas.buscar_por_prioridad(comando.usuario_id, prioridad) is not None:
            raise PrioridadDuplicada(
                f"Ya tenés otra regla con prioridad {prioridad}: el motor de categorización "
                "necesita un orden sin empates."
            )

        regla = ReglaCategorizacion(
            usuario_id=comando.usuario_id,
            categoria_destino_id=categoria.id,
            nombre=nombre,
            campo=comando.campo,
            patron=patron,
            prioridad=prioridad,
            activa=True,
            veces_aplicada=0,
        )
        self.reglas.agregar(regla)
        self.reglas.sesion.commit()
        return regla

    def nombre_de_categoria(self, categoria_id: int) -> str | None:
        """El nombre de la categoría destino de una regla, para armar la respuesta.

        Sin `usuario_id`: `categoria_destino_id` ya quedó validado como del
        titular al crear la regla -no es un id libre que alguien pueda pasar.
        """
        categoria = self.categorias.obtener_por_id(categoria_id)
        return categoria.nombre if categoria else None

    def listar(self, usuario_id: int) -> list[ReglaCategorizacion]:
        """Todas las reglas del titular, activas e inactivas, en orden de prioridad."""
        self._asegurar_usuario_activo(usuario_id)
        return self.reglas.listar_de_usuario(usuario_id)

    def obtener(self, usuario_id: int, regla_id: int) -> ReglaCategorizacion:
        """La regla, solo si pertenece al titular que la pide."""
        return self._obtener_del_titular(usuario_id, regla_id)

    def desactivar(self, usuario_id: int, regla_id: int) -> ReglaCategorizacion:
        """Desactiva una regla -nunca se borra: conserva `veces_aplicada` como historial,
        y una compra ya conciliada con ella no pierde de dónde salió su categoría."""
        regla = self._obtener_del_titular(usuario_id, regla_id)
        regla.activa = False
        self.reglas.sesion.commit()
        return regla

    def _obtener_del_titular(self, usuario_id: int, regla_id: int) -> ReglaCategorizacion:
        self._asegurar_usuario_activo(usuario_id)
        regla = self.reglas.obtener_de_usuario(regla_id, usuario_id)
        if regla is None:
            raise RecursoNoEncontrado(f"La regla {regla_id} no existe en esta cuenta.")
        return regla

    def _asegurar_usuario_activo(self, usuario_id: int) -> None:
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        if not usuario.activo:
            raise UsuarioInactivo(f"El usuario {usuario_id} esta desactivado.")
