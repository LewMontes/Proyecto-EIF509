"""Motor de conexion, sesion por peticion y creacion del esquema."""

from collections.abc import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import obtener_configuracion
from app.data.models.base import Base
from app.data.models.categoria_estandar import CategoriaEstandar

# Mismos códigos/nombres/colores que db/postgres/seeds/afterMigrate__datos_de_ejemplo.sql
# -es la misma taxonomía del Laboratorio 2, tal cual, ahora sembrada por la
# app en vivo en vez de solo por el seed de Flyway.
_CATEGORIAS_ESTANDAR = [
    ("ALIMENTACION", "Alimentacion", "Todo lo que se come y se bebe", "#16A34A", 1),
    ("SUPERMERCADO", "Supermercado", "Compras de abarrotes y canasta basica", "#22C55E", 2),
    (
        "RESTAURANTES",
        "Restaurantes y sodas",
        "Comidas fuera de casa y pedidos a domicilio",
        "#4ADE80",
        3,
    ),  # noqa: E501
    ("TRANSPORTE", "Transporte", "Traslados y mantenimiento del vehiculo", "#2563EB", 4),
    ("COMBUSTIBLE", "Combustible", "Gasolina y diesel", "#3B82F6", 5),
    ("SALUD", "Salud", "Consultas, examenes y tratamientos", "#DC2626", 6),
    ("FARMACIA", "Farmacia", "Medicamentos y productos de botiquin", "#EF4444", 7),
    ("HOGAR", "Hogar", "Limpieza, ferreteria y mantenimiento de la casa", "#D97706", 8),
    (
        "SERVICIOS_PUBLICOS",
        "Servicios publicos",
        "Electricidad, agua, internet y telefonia",
        "#F59E0B",
        9,
    ),  # noqa: E501
    (
        "SUSCRIPCIONES",
        "Suscripciones",
        "Servicios recurrentes, casi siempre en dolares",
        "#9333EA",
        10,
    ),  # noqa: E501
    ("ENTRETENIMIENTO", "Entretenimiento", "Cine, conciertos, paseos y salidas", "#C026D3", 11),
    ("EDUCACION", "Educacion", "Matriculas, cursos y materiales de estudio", "#0891B2", 12),
    ("ROPA", "Ropa y calzado", "Vestimenta y accesorios", "#DB2777", 13),
    ("MASCOTAS", "Mascotas", "Alimento, veterinario y accesorios", "#65A30D", 14),
    ("OTROS", "Otros", "Gasto que todavia no encaja en ninguna categoria", "#6B7280", 15),
]

_configuracion = obtener_configuracion()

# check_same_thread solo aplica a SQLite: uvicorn atiende las peticiones en un
# pool de hilos y SQLite, por defecto, prohibe usar la conexion desde otro hilo.
_argumentos_conexion = (
    {"check_same_thread": False} if _configuracion.url_base_datos.startswith("sqlite") else {}
)

motor = create_engine(_configuracion.url_base_datos, connect_args=_argumentos_conexion)

FabricaDeSesiones = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


def crear_tablas() -> None:
    """Crea el esquema si no existe, en SQLite o en PostgreSQL según `url_base_datos`.

    No hay migraciones versionadas para este esquema todavía: `create_all`
    crea lo que falte pero nunca altera una columna existente, así que un
    cambio de modelo no se propaga solo a una base que ya tenía la tabla
    vieja. Mientras el proyecto siga en una sola persona por ambiente esto
    alcanza; herramientas como Alembic entran cuando eso deje de ser cierto.
    """
    Base.metadata.create_all(bind=motor)


def sembrar_categorias_estandar() -> None:
    """Deja creadas las ~15 filas de `categoria_estandar`, si todavía no existen.

    Es la taxonomía global compartida -no una por usuario- así que se siembra
    una sola vez a nivel de sistema, no por cada `Usuario` que se registra.
    `CategoriaService.sembrar_estandar` (que sí corre por usuario, al
    registrarse) las usa para armar la jerarquía inicial de cada cuenta
    nueva. `ON CONFLICT`-like: se salta cualquier código que ya exista, así
    que correr esto de nuevo -en una base que ya tenía datos de antes de que
    existiera esta siembra- no duplica nada.
    """
    with FabricaDeSesiones() as sesion:
        existentes = set(sesion.scalars(select(CategoriaEstandar.codigo)))
        nuevas = [
            CategoriaEstandar(
                codigo=codigo, nombre=nombre, descripcion=descripcion, color_hex=color, orden=orden
            )
            for codigo, nombre, descripcion, color, orden in _CATEGORIAS_ESTANDAR
            if codigo not in existentes
        ]
        if not nuevas:
            return
        sesion.add_all(nuevas)
        sesion.commit()


def obtener_sesion() -> Iterator[Session]:
    """Entrega una sesion por peticion y la cierra siempre, pase lo que pase.

    Nunca confirma: el commit es responsabilidad de la capa de negocio, que es la
    unica que sabe si la operacion completa termino bien.
    """
    sesion = FabricaDeSesiones()
    try:
        yield sesion
    finally:
        sesion.close()
