"""Reglas de negocio del catálogo de comercios y su categoría sugerida."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.business.errors import (
    CategoriaNoEsHoja,
    ComercioYaExiste,
    DatosInvalidos,
    RecursoNoEncontrado,
)
from app.business.parsers.comprobante_bac import ComprobanteParseado
from app.data.models.comercio import Comercio
from app.data.models.comercio_categoria_sugerida import ComercioCategoriaSugerida
from app.data.paginacion import Pagina, SolicitudDePagina
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository


def normalizar_nombre_comercio(nombre: str) -> str:
    """Uppercase, sin acentos, espacios colapsados: la clave de identidad del comercio.

    `Walmart  San Sebastián` y `WALMART SAN SEBASTIAN` tienen que resolver al
    mismo registro; sin normalizar, cada variante de mayúsculas o acentos del
    nombre que llega en un comprobante crearía un comercio duplicado.
    """
    sin_acentos = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().upper()


@dataclass(frozen=True)
class ComercioClasificado:
    """Un comercio real, resuelto del catálogo, con lo gastado ahí en el período leído."""

    comercio_id: int
    nombre: str
    categoria_id: int | None
    categoria_nombre: str | None
    cantidad_transacciones: int
    total: Decimal
    moneda: str


@dataclass(frozen=True)
class MovimientoDetallado:
    """Un comprobante real, sin agrupar, con su comercio resuelto y su categoría."""

    fecha: datetime
    comercio: str
    categoria_nombre: str | None
    monto: Decimal
    moneda: str
    marca_tarjeta: str | None
    ultimos_cuatro: str | None
    ciudad: str | None
    pais: str | None
    banco: str
    autorizacion: str | None
    referencia: str | None


class ComercioService:
    """Resuelve comercios del catálogo compartido y sus categorías sugeridas por titular."""

    CAMPOS_ORDENABLES = tuple(ComercioRepository.COLUMNAS_ORDENABLES)

    def __init__(
        self,
        comercio_repository: ComercioRepository,
        comercio_categoria_repository: ComercioCategoriaRepository,
        categoria_repository: CategoriaRepository,
    ) -> None:
        self.comercios = comercio_repository
        self.sugerencias = comercio_categoria_repository
        self.categorias = categoria_repository

    def resolver_o_crear(self, nombre: str) -> Comercio:
        """Busca el comercio por su nombre normalizado, o lo crea si es la primera vez que se ve."""
        nombre = nombre.strip()
        if not nombre:
            raise DatosInvalidos("El nombre del comercio no puede venir vacío.")
        normalizado = normalizar_nombre_comercio(nombre)
        comercio = self.comercios.buscar_por_nombre_normalizado(normalizado)
        if comercio is not None:
            return comercio
        comercio = Comercio(nombre=nombre, nombre_normalizado=normalizado)
        self.comercios.agregar(comercio)
        self.comercios.sesion.commit()
        return comercio

    def crear(
        self,
        nombre: str,
        identificacion_tributaria: str | None = None,
        provincia: str | None = None,
    ) -> Comercio:
        """Da de alta un comercio en el catálogo compartido.

        A diferencia de `resolver_o_crear` -que usa la ingesta y reutiliza el
        que ya exista- esto es una alta explícita de quien administra el
        catálogo: si el nombre normalizado ya está, se rechaza en vez de
        devolver el existente en silencio.
        """
        nombre = nombre.strip()
        if not nombre:
            raise DatosInvalidos("El nombre del comercio no puede venir vacío.")
        normalizado = normalizar_nombre_comercio(nombre)
        if self.comercios.buscar_por_nombre_normalizado(normalizado) is not None:
            raise ComercioYaExiste(f"Ya existe el comercio '{normalizado}' en el catálogo.")
        if identificacion_tributaria is not None and not (
            identificacion_tributaria.isdigit() and 9 <= len(identificacion_tributaria) <= 12
        ):
            raise DatosInvalidos("La identificación tributaria debe tener entre 9 y 12 dígitos.")
        comercio = Comercio(
            nombre=nombre,
            nombre_normalizado=normalizado,
            identificacion_tributaria=identificacion_tributaria,
            provincia=provincia.strip() if provincia else None,
        )
        self.comercios.agregar(comercio)
        self.comercios.sesion.commit()
        return comercio

    def buscar(self, nombre: str | None, solicitud: SolicitudDePagina) -> Pagina[Comercio]:
        """Una página del catálogo compartido, opcionalmente filtrada por nombre.

        El texto se normaliza igual que los nombres del catálogo, así que
        buscar `sebastián` encuentra `WALMART SAN SEBASTIAN`.
        """
        nombre_normalizado = normalizar_nombre_comercio(nombre) if nombre else None
        return self.comercios.buscar(nombre_normalizado, solicitud)

    def obtener(self, comercio_id: int) -> Comercio:
        comercio = self.comercios.obtener_por_id(comercio_id)
        if comercio is None:
            raise RecursoNoEncontrado(f"El comercio {comercio_id} no existe.")
        return comercio

    def categoria_sugerida_para(self, usuario_id: int, comercio_id: int) -> int | None:
        """El id de la categoría que este titular le asignó a este comercio, si la hay."""
        sugerencia = self.sugerencias.buscar(usuario_id, comercio_id)
        return sugerencia.categoria_id if sugerencia else None

    def resolver_con_categoria(
        self, usuario_id: int, nombre_comercio: str
    ) -> tuple[Comercio, str | None]:
        """Resuelve el comercio y el nombre de categoría que este titular le asignó, si la hay."""
        comercio = self.resolver_o_crear(nombre_comercio)
        categoria_id = self.categoria_sugerida_para(usuario_id, comercio.id)
        categoria_nombre = None
        if categoria_id is not None:
            categoria = self.categorias.obtener_por_id(categoria_id)
            categoria_nombre = categoria.nombre if categoria else None
        return comercio, categoria_nombre

    def asignar_categoria(
        self, usuario_id: int, comercio_id: int, categoria_id: int
    ) -> ComercioCategoriaSugerida:
        """Asigna o corrige la categoría sugerida de un comercio para un titular.

        Es "corregir crea la regla": la próxima vez que este comercio aparezca
        en un comprobante de este mismo titular, esta es la categoría que se
        va a sugerir. No afecta a ningún otro titular que compre en el mismo
        comercio -la sugerencia es siempre por `(usuario, comercio)`.
        """
        self.obtener(comercio_id)

        categoria = self.categorias.obtener_de_usuario(categoria_id, usuario_id)
        if categoria is None:
            raise RecursoNoEncontrado(
                f"La categoría {categoria_id} no existe en la cuenta de este titular."
            )
        if not categoria.es_hoja:
            raise CategoriaNoEsHoja(
                f"'{categoria.nombre}' es una categoría padre; solo se puede sugerir una hoja, "
                "porque las categorías padre totalizan y no reciben gasto directo."
            )

        sugerencia = self.sugerencias.buscar(usuario_id, comercio_id)
        if sugerencia is None:
            sugerencia = ComercioCategoriaSugerida(
                usuario_id=usuario_id, comercio_id=comercio_id, categoria_id=categoria_id
            )
            self.sugerencias.agregar(sugerencia)
        else:
            sugerencia.categoria_id = categoria_id

        self.sugerencias.sesion.commit()
        return sugerencia

    def clasificar_comprobantes(
        self, usuario_id: int, comprobantes: list[ComprobanteParseado]
    ) -> list[ComercioClasificado]:
        """Agrupa comprobantes ya parseados por comercio y moneda, resolviendo cada
        comercio en el catálogo y adjuntando la categoría sugerida de este titular.

        Igual que en `resumen_service.agrupar_por_mes`, las monedas nunca se
        mezclan: un comercio que cobró una vez en colones y otra en dólares
        aparece como dos filas, no una suma inventada.
        """
        acumulado: dict[tuple[str, str], tuple[Decimal, int]] = {}
        for comprobante in comprobantes:
            if not (
                comprobante.es_compra
                and comprobante.es_confiable
                and comprobante.comercio
                and comprobante.monto is not None
                and comprobante.moneda
            ):
                continue
            clave = (comprobante.comercio, comprobante.moneda)
            total_previo, cantidad_previa = acumulado.get(clave, (Decimal("0"), 0))
            acumulado[clave] = (total_previo + comprobante.monto, cantidad_previa + 1)

        resultado = []
        for (nombre_comercio, moneda), (total, cantidad) in acumulado.items():
            comercio, categoria_nombre = self.resolver_con_categoria(usuario_id, nombre_comercio)
            categoria_id = self.categoria_sugerida_para(usuario_id, comercio.id)
            resultado.append(
                ComercioClasificado(
                    comercio_id=comercio.id,
                    nombre=comercio.nombre,
                    categoria_id=categoria_id,
                    categoria_nombre=categoria_nombre,
                    cantidad_transacciones=cantidad,
                    total=total,
                    moneda=moneda,
                )
            )
        resultado.sort(key=lambda r: r.total, reverse=True)
        return resultado

    def detallar_comprobantes(
        self, usuario_id: int, comprobantes: list[ComprobanteParseado]
    ) -> list[MovimientoDetallado]:
        """Un renglón por comprobante real -sin agrupar-, con el comercio resuelto y su categoría.

        Es la fuente de los reportes de detalle: a diferencia de
        `clasificar_comprobantes`, no suma nada, así que conserva la fecha,
        la autorización y la referencia de cada movimiento individual.
        """
        detalle = []
        for comprobante in comprobantes:
            if not (
                comprobante.es_compra
                and comprobante.es_confiable
                and comprobante.comercio
                and comprobante.monto is not None
                and comprobante.moneda
                and comprobante.fecha
            ):
                continue
            _, categoria_nombre = self.resolver_con_categoria(usuario_id, comprobante.comercio)
            detalle.append(
                MovimientoDetallado(
                    fecha=comprobante.fecha,
                    comercio=comprobante.comercio,
                    categoria_nombre=categoria_nombre,
                    monto=comprobante.monto,
                    moneda=comprobante.moneda,
                    marca_tarjeta=comprobante.marca_tarjeta,
                    ultimos_cuatro=comprobante.ultimos_cuatro,
                    ciudad=comprobante.ciudad,
                    pais=comprobante.pais,
                    banco=comprobante.banco,
                    autorizacion=comprobante.autorizacion,
                    referencia=comprobante.referencia,
                )
            )
        detalle.sort(key=lambda m: m.fecha, reverse=True)
        return detalle
