"""Punto de entrada de la aplicacion.

Arranca con:  uvicorn app.main:app --reload --app-dir src
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.database import crear_tablas, sembrar_administrador, sembrar_categorias_estandar
from app.config.settings import obtener_configuracion
from app.presentation.errores import (
    RESPUESTAS_DE_ERROR,
    documentar_errores_como_problem_details,
    registrar_manejadores_de_error,
)
from app.presentation.routers import (
    auth,
    categorias,
    comercios,
    compras,
    comprobantes,
    cuentas_correo,
    metodos_pago,
    presupuestos,
    reglas_categorizacion,
    salud,
    usuarios,
)

DESCRIPCION_DE_LA_API = """
API REST de **Gastonomo**: el contrato público de la capa de negocio.

### Cómo usarla desde esta página

1. Creá una cuenta con `POST /api/v1/usuarios`.
2. Pedí el token con `POST /api/v1/auth/login`.
3. Pegá el `access_token` en **Authorize** (arriba a la derecha). Desde ahí, cada
   petición lleva `Authorization: Bearer <token>`.

### Convenciones del contrato

- **Versión en la ruta**: todo vive bajo `/api/v1`.
- **Stateless**: no hay sesión de servidor; cada petición se autentica con su token.
- **El titular sale del token**: ningún endpoint acepta `usuario_id`.
- **Dos roles**: `TITULAR` administra sus datos; `ADMIN` mantiene el catálogo
  compartido de comercios y la lista de cuentas.
- **Errores**: siempre `application/problem+json` (RFC 9457).
  `400` formato inválido · `401` sin token válido · `403` rol insuficiente ·
  `404` no existe o no es tuyo · `409` choca con el estado del recurso ·
  `422` rompe una regla del dominio.
- **Colecciones**: `?pagina=0&tamano=20&orden=campo,desc`, con metadatos en la respuesta.
"""

ETIQUETAS = [
    {"name": "salud", "description": "Si la aplicación está viva. Público y sin versión."},
    {"name": "auth", "description": "Emisión del token de acceso."},
    {"name": "usuarios", "description": "Registro y consulta de cuentas."},
    {"name": "categorias", "description": "La jerarquía de clasificación de cada titular."},
    {"name": "comercios", "description": "Catálogo compartido. Solo `ADMIN` lo da de alta."},
    {"name": "metodos-pago", "description": "Tarjetas y medios de pago del titular."},
    {"name": "presupuestos", "description": "Tope de gasto por categoría y mes."},
    {"name": "reglas-categorizacion", "description": "Reglas que clasifican solas una compra."},
    {
        "name": "compras",
        "description": "**Proceso 1** · registro manual con desglose. Y la colección paginada.",
    },
    {"name": "cuentas-correo", "description": "Los buzones de los que vienen los comprobantes."},
    {
        "name": "comprobantes",
        "description": "**Proceso 2** · ingesta y conciliación transaccional de un comprobante.",
    },
]


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    """Prepara la base al arrancar."""
    crear_tablas()
    sembrar_categorias_estandar()
    sembrar_administrador()
    yield


def crear_app() -> FastAPI:
    """Fabrica de la aplicacion.

    Se usa una funcion en vez de un app global para poder crear instancias
    limpias en las pruebas sin arrastrar configuracion de una a otra.
    """
    configuracion = obtener_configuracion()

    app = FastAPI(
        title=configuracion.nombre_aplicacion,
        version=configuracion.version,
        summary="Control de gastos personales por categorías · EIF509 · Grupo G01",
        description=DESCRIPCION_DE_LA_API,
        openapi_tags=ETIQUETAS,
        lifespan=ciclo_de_vida,
        # Swagger UI recuerda el token entre recargas de la página: sin esto
        # hay que volver a pegarlo en «Authorize» cada vez.
        swagger_ui_parameters={"persistAuthorization": True},
    )

    # El frontend React correra en otro puerto durante el desarrollo.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(salud.router)
    # Todo lo que vive bajo /api/v1 declara, además de su respuesta exitosa, los
    # errores que puede devolver: así quedan en el contrato OpenAPI con su forma
    # real (Problem Details) y no con la que FastAPI documenta por defecto.
    for router in (
        auth.router,
        usuarios.router,
        categorias.router,
        comercios.router,
        metodos_pago.router,
        presupuestos.router,
        reglas_categorizacion.router,
        compras.router,
        cuentas_correo.router,
        comprobantes.router,
    ):
        app.include_router(router, responses=RESPUESTAS_DE_ERROR)

    registrar_manejadores_de_error(app)
    documentar_errores_como_problem_details(app)
    return app


app = crear_app()
