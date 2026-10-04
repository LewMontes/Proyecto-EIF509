"""Reglas de negocio de las categorias."""

import re
from dataclasses import dataclass

from app.business.errors import (
    CategoriaConSubcategorias,
    CategoriaInactiva,
    DatosInvalidos,
    NombreDuplicado,
    RecursoNoEncontrado,
    UsuarioInactivo,
)
from app.data.models.categoria import Categoria
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.usuario_repository import UsuarioRepository

LARGO_MAXIMO_NOMBRE = 60
PATRON_COLOR_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Jerarquía fija con la que se siembra la cuenta de todo titular nuevo, tomada
# tal cual del seed de Flyway (db/postgres/seeds/afterMigrate__datos_de_ejemplo.sql):
# 3 categorías padre con sus hijas, el resto como hojas sueltas. El código -no
# el nombre- es la llave estable de `categoria_estandar`.
_JERARQUIA_ESTANDAR: dict[str, list[str]] = {
    "ALIMENTACION": ["SUPERMERCADO", "RESTAURANTES"],
    "TRANSPORTE": ["COMBUSTIBLE"],
    "SALUD": ["FARMACIA"],
}
_HOJAS_SUELTAS = (
    "HOGAR",
    "SERVICIOS_PUBLICOS",
    "SUSCRIPCIONES",
    "ENTRETENIMIENTO",
    "EDUCACION",
    "ROPA",
    "MASCOTAS",
    "OTROS",
)


@dataclass(frozen=True)
class CrearCategoriaComando:
    """Orden que recibe el negocio para crear una categoria.

    Es una dataclass propia y no un modelo de Pydantic a proposito: si el
    servicio recibiera modelos de FastAPI, el negocio quedaria amarrado a la
    forma de la API y no se podria reutilizar desde otro punto de entrada.
    """

    usuario_id: int
    nombre: str
    color_hex: str
    descripcion: str | None = None
    categoria_padre_id: int | None = None


@dataclass(frozen=True)
class ActualizarCategoriaComando:
    """Orden para corregir una categoria que ya existe.

    No trae `categoria_padre_id`: mover una categoria dentro de la jerarquia
    cambia cuales son hoja y cuales totalizan, y eso es otra operacion.
    """

    usuario_id: int
    categoria_id: int
    nombre: str
    color_hex: str
    descripcion: str | None = None


class CategoriaService:
    """Aplica las reglas del dominio y decide cuando confirmar la transaccion."""

    def __init__(
        self,
        categoria_repository: CategoriaRepository,
        usuario_repository: UsuarioRepository,
        categoria_estandar_repository: CategoriaEstandarRepository,
    ) -> None:
        self.categorias = categoria_repository
        self.usuarios = usuario_repository
        self.estandar = categoria_estandar_repository

    def crear(self, comando: CrearCategoriaComando) -> Categoria:
        """Crea una categoria de un usuario.

        Reglas que aplica:
        - El nombre no puede venir vacio ni pasar de 60 caracteres.
        - El color debe ser hexadecimal (#RRGGBB): lo consumen los graficos.
        - El titular debe existir y estar activo.
        - No puede repetirse el nombre dentro de la misma cuenta.
        - La categoria padre debe existir, estar activa y ser del mismo titular.
        - Colgarle una hija a una categoria la convierte en categoria padre, y
          las padre dejan de recibir gasto directo: pasan a totalizar.
        """
        nombre = comando.nombre.strip()
        if not nombre:
            raise DatosInvalidos("El nombre de la categoria no puede venir vacio.")
        if len(nombre) > LARGO_MAXIMO_NOMBRE:
            raise DatosInvalidos(
                f"El nombre de la categoria no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres."
            )
        if not PATRON_COLOR_HEX.match(comando.color_hex):
            raise DatosInvalidos(
                f"El color '{comando.color_hex}' no es hexadecimal valido. Se espera #RRGGBB."
            )

        self._asegurar_usuario_activo(comando.usuario_id)

        if self.categorias.buscar_por_nombre(comando.usuario_id, nombre) is not None:
            raise NombreDuplicado(f"Ya existe una categoria llamada '{nombre}' en la cuenta.")

        categoria_padre = None
        if comando.categoria_padre_id is not None:
            categoria_padre = self.categorias.obtener_de_usuario(
                comando.categoria_padre_id, comando.usuario_id
            )
            if categoria_padre is None:
                raise RecursoNoEncontrado(
                    f"La categoria padre {comando.categoria_padre_id} no existe en esta cuenta."
                )
            if not categoria_padre.activa:
                raise CategoriaInactiva(
                    f"La categoria padre '{categoria_padre.nombre}' esta desactivada."
                )
            categoria_padre.es_hoja = False

        categoria = Categoria(
            usuario_id=comando.usuario_id,
            nombre=nombre,
            descripcion=comando.descripcion,
            color_hex=comando.color_hex.upper(),
            categoria_padre_id=comando.categoria_padre_id,
            es_hoja=True,
            activa=True,
        )
        self.categorias.agregar(categoria)

        # El commit vive aqui, no en el repositorio: este es el unico punto que
        # sabe que la operacion completa -incluido el cambio en la padre- cuadro.
        self.categorias.sesion.commit()
        return categoria

    def sembrar_estandar(self, usuario_id: int) -> list[Categoria]:
        """Crea la jerarquía inicial de un titular nuevo a partir de `CategoriaEstandar`.

        "Para que nadie arranque con una lista vacía" -la propuesta de
        dominio original. Se llama una sola vez, desde `AuthService.registrar`,
        justo después de crear el `Usuario`. Si las 15 filas de
        `categoria_estandar` todavía no existen en esta base -una base nueva
        antes de que arranque `crear_tablas()`/la siembra a nivel de sistema-
        simplemente no crea nada: no es un error, es una cuenta que arranca
        sin catálogo semilla y puede crear sus categorías a mano igual que
        antes de que existiera esta función.
        """
        por_codigo = {ce.codigo: ce for ce in self.estandar.listar_ordenadas()}
        if not por_codigo:
            return []

        creadas: dict[str, Categoria] = {}

        def crear(codigo: str, padre: Categoria | None) -> Categoria | None:
            estandar = por_codigo.get(codigo)
            if estandar is None:
                return None
            categoria = Categoria(
                usuario_id=usuario_id,
                categoria_padre_id=padre.id if padre else None,
                categoria_estandar_id=estandar.id,
                nombre=estandar.nombre,
                descripcion=estandar.descripcion,
                color_hex=estandar.color_hex,
                es_hoja=True,
                activa=True,
            )
            self.categorias.agregar(categoria)  # flush: ya tiene id para ser padre de una hija
            creadas[codigo] = categoria
            return categoria

        for codigo_padre, codigos_hijos in _JERARQUIA_ESTANDAR.items():
            padre = crear(codigo_padre, None)
            if padre is None:
                continue
            for codigo_hijo in codigos_hijos:
                if crear(codigo_hijo, padre) is not None:
                    padre.es_hoja = False

        for codigo in _HOJAS_SUELTAS:
            crear(codigo, None)

        self.categorias.sesion.commit()
        return list(creadas.values())

    def obtener(self, usuario_id: int, categoria_id: int) -> Categoria:
        """La categoria, solo si pertenece al titular que la pide."""
        self._asegurar_usuario_activo(usuario_id)
        categoria = self.categorias.obtener_de_usuario(categoria_id, usuario_id)
        if categoria is None:
            raise RecursoNoEncontrado(f"La categoria {categoria_id} no existe en esta cuenta.")
        return categoria

    def actualizar(self, comando: ActualizarCategoriaComando) -> Categoria:
        """Corrige el nombre, el color y la descripcion de una categoria del titular.

        Aplica las mismas reglas de forma que `crear`, y el nombre no puede
        chocar con el de **otra** categoria de la cuenta -si puede quedarse
        con el suyo.
        """
        categoria = self.obtener(comando.usuario_id, comando.categoria_id)

        nombre = comando.nombre.strip()
        if not nombre:
            raise DatosInvalidos("El nombre de la categoria no puede venir vacio.")
        if len(nombre) > LARGO_MAXIMO_NOMBRE:
            raise DatosInvalidos(
                f"El nombre de la categoria no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres."
            )
        if not PATRON_COLOR_HEX.match(comando.color_hex):
            raise DatosInvalidos(
                f"El color '{comando.color_hex}' no es hexadecimal valido. Se espera #RRGGBB."
            )
        existente = self.categorias.buscar_por_nombre(comando.usuario_id, nombre)
        if existente is not None and existente.id != categoria.id:
            raise NombreDuplicado(f"Ya existe una categoria llamada '{nombre}' en la cuenta.")

        categoria.nombre = nombre
        categoria.color_hex = comando.color_hex.upper()
        categoria.descripcion = comando.descripcion
        self.categorias.sesion.commit()
        return categoria

    def desactivar(self, usuario_id: int, categoria_id: int) -> None:
        """Desactiva una categoria -nunca se borra: el gasto historico la sigue mostrando.

        Una categoria padre no se desactiva mientras tenga subcategorias
        activas: quedarian colgando de un grupo que ya no aparece. Si era la
        ultima hija activa de su padre, el padre vuelve a ser hoja.
        """
        categoria = self.obtener(usuario_id, categoria_id)
        if self.categorias.tiene_hijas_activas(categoria.id):
            raise CategoriaConSubcategorias(
                f"'{categoria.nombre}' tiene subcategorias activas: desactivalas primero."
            )
        categoria.activa = False
        if categoria.categoria_padre_id is not None:
            self.categorias.sesion.flush()
            if not self.categorias.tiene_hijas_activas(categoria.categoria_padre_id):
                padre = self.categorias.obtener_por_id(categoria.categoria_padre_id)
                if padre is not None:
                    padre.es_hoja = True
        self.categorias.sesion.commit()

    def listar_activas(self, usuario_id: int) -> list[Categoria]:
        """Lista las categorias activas de un usuario."""
        self._asegurar_usuario_activo(usuario_id)
        return self.categorias.listar_activas_de_usuario(usuario_id)

    def _asegurar_usuario_activo(self, usuario_id: int) -> None:
        usuario = self.usuarios.obtener_por_id(usuario_id)
        if usuario is None:
            raise RecursoNoEncontrado(f"El usuario {usuario_id} no existe.")
        if not usuario.activo:
            raise UsuarioInactivo(f"El usuario {usuario_id} esta desactivado.")
