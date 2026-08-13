"""Reglas de negocio de las categorias.

Las categorias son el eje del sistema: todo el gasto se clasifica contra ellas.
Este servicio concentra las reglas que deben cumplirse al crearlas.

El servicio es el dueno de la transaccion. El repositorio solo agrega y consulta;
confirmar o revertir lo decide aqui, porque el servicio es el unico que sabe si
la operacion de negocio completa termino bien. Ese limite es el que mas adelante
sostiene el proceso de conciliacion, que escribe en cinco tablas y tiene que
ocurrir todo o nada.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.business.errors import RecursoNoEncontrado, ReglaDeNegocioViolada, ValidacionFallida
from app.data.models.categoria import Categoria
from app.data.repositories.categoria_repository import CategoriaRepository

LARGO_MAXIMO_NOMBRE = 80


@dataclass(frozen=True)
class CrearCategoriaComando:
    """Orden que recibe el negocio.

    Es una dataclass propia y no un modelo de FastAPI a proposito: si el servicio
    recibiera modelos de la API, la capa de negocio quedaria amarrada a la forma
    del HTTP y no se podria reutilizar desde un script o una tarea programada.
    """

    usuario_id: int
    nombre: str
    descripcion: str | None = None
    color_hex: str = "#6B7280"
    categoria_padre_id: int | None = None


class CategoriaService:
    def __init__(self, repositorio: CategoriaRepository) -> None:
        self._repositorio = repositorio

    def crear(self, comando: CrearCategoriaComando) -> Categoria:
        """Crea una categoria aplicando todas las reglas del dominio."""
        nombre = self._validar_nombre(comando.nombre)
        self._validar_color(comando.color_hex)
        self._validar_nombre_disponible(comando.usuario_id, nombre)

        padre = self._resolver_padre(comando.usuario_id, comando.categoria_padre_id)
        if padre is not None:
            # Una categoria que pasa a tener hijas deja de recibir gasto directo:
            # de ahora en adelante solo totaliza lo que gastan sus subcategorias.
            padre.es_hoja = False

        categoria = self._repositorio.agregar(
            Categoria(
                usuario_id=comando.usuario_id,
                nombre=nombre,
                descripcion=comando.descripcion,
                color_hex=comando.color_hex.upper(),
                categoria_padre_id=comando.categoria_padre_id,
                es_hoja=True,
                activa=True,
            )
        )
        # La categoria nueva y el cambio de es_hoja de su padre se confirman
        # juntos: si el padre quedara marcado como hoja sin su subcategoria,
        # el arbol de categorias quedaria mintiendo.
        self._repositorio.session.commit()
        return categoria

    def listar(self, usuario_id: int) -> list[Categoria]:
        return self._repositorio.listar_por_usuario(usuario_id)

    # ------------------------------------------------------------------
    #  Reglas y validaciones
    # ------------------------------------------------------------------
    def _validar_nombre(self, nombre: str) -> str:
        limpio = nombre.strip()
        if not limpio:
            raise ValidacionFallida("El nombre de la categoria no puede estar vacio.")
        if len(limpio) > LARGO_MAXIMO_NOMBRE:
            raise ValidacionFallida(
                f"El nombre no puede pasar de {LARGO_MAXIMO_NOMBRE} caracteres."
            )
        return limpio

    def _validar_color(self, color_hex: str) -> None:
        """El frontend pinta los graficos con este color, asi que debe ser valido."""
        if len(color_hex) != 7 or not color_hex.startswith("#"):
            raise ValidacionFallida(
                "El color debe venir en formato hexadecimal, por ejemplo #2563EB."
            )
        try:
            int(color_hex[1:], 16)
        except ValueError as error:
            raise ValidacionFallida(f"'{color_hex}' no es un color hexadecimal valido.") from error

    def _validar_nombre_disponible(self, usuario_id: int, nombre: str) -> None:
        """Regla: dos categorias del mismo usuario no pueden llamarse igual.

        Si se permitiera, el usuario no podria distinguirlas al clasificar un
        gasto y sus reportes quedarian partidos entre dos categorias identicas.
        """
        if self._repositorio.buscar_por_nombre(usuario_id, nombre) is not None:
            raise ReglaDeNegocioViolada(f"Ya existe una categoria llamada '{nombre}'.")

    def _resolver_padre(self, usuario_id: int, padre_id: int | None) -> Categoria | None:
        """Regla: la categoria padre debe existir, estar activa y ser del mismo usuario.

        La validacion de pertenencia es lo que impide que alguien cuelgue una
        categoria suya de la de otra persona pasando un id ajeno.
        """
        if padre_id is None:
            return None

        padre = self._repositorio.obtener_por_id(padre_id)
        if padre is None or padre.usuario_id != usuario_id:
            raise RecursoNoEncontrado(f"No existe la categoria padre {padre_id}.")
        if not padre.activa:
            raise ReglaDeNegocioViolada("No se puede colgar una categoria de una padre inactiva.")
        return padre
