"""Punto de entrada de la aplicacion.

Arranca con:  uvicorn app.main:app --reload --app-dir src
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.business.errors import (
    AccesoDenegado,
    DatosInvalidos,
    ErrorDeProveedorExterno,
    NoAutenticado,
    RecursoNoEncontrado,
    ReglaDeNegocioViolada,
)
from app.config.database import crear_tablas, sembrar_administrador, sembrar_categorias_estandar
from app.config.settings import obtener_configuracion
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
        description="Tracker de compras personales por categorias - EIF509",
        lifespan=ciclo_de_vida,
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
    app.include_router(auth.router)
    app.include_router(usuarios.router)
    app.include_router(categorias.router)
    app.include_router(comercios.router)
    app.include_router(metodos_pago.router)
    app.include_router(presupuestos.router)
    app.include_router(reglas_categorizacion.router)
    app.include_router(compras.router)
    app.include_router(cuentas_correo.router)
    app.include_router(comprobantes.router)

    registrar_manejadores_de_error(app)
    return app


def registrar_manejadores_de_error(app: FastAPI) -> None:
    """Traduce los errores de negocio a codigos HTTP.

    Esta traduccion es responsabilidad de la capa de presentacion: es el unico
    lugar del sistema al que se le permite saber que existen los codigos HTTP.
    Se registra un manejador por **familia** de error; las reglas con nombre
    (`CategoriaNoEsHoja`, `CuadreFueraDeTolerancia`...) heredan de su familia y
    caen en el manejador de ella.
    """

    @app.exception_handler(DatosInvalidos)
    def _datos_invalidos(_: Request, error: DatosInvalidos) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detalle": str(error)})

    @app.exception_handler(ReglaDeNegocioViolada)
    def _regla(_: Request, error: ReglaDeNegocioViolada) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detalle": str(error)})

    @app.exception_handler(RecursoNoEncontrado)
    def _no_encontrado(_: Request, error: RecursoNoEncontrado) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detalle": str(error)})

    @app.exception_handler(NoAutenticado)
    def _no_autenticado(_: Request, error: NoAutenticado) -> JSONResponse:
        """401, con el encabezado que le dice al cliente como autenticarse."""
        return JSONResponse(
            status_code=401,
            content={"detalle": str(error)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AccesoDenegado)
    def _acceso_denegado(_: Request, error: AccesoDenegado) -> JSONResponse:
        """403, no 401: se sabe quien es; lo que falla es lo que pide."""
        return JSONResponse(status_code=403, content={"detalle": str(error)})

    @app.exception_handler(ErrorDeProveedorExterno)
    def _proveedor_externo(_: Request, error: ErrorDeProveedorExterno) -> JSONResponse:
        """502, no 4xx: que el Banco Central este caido no significa que el
        cliente se haya equivocado, y un 4xx le diria exactamente eso."""
        return JSONResponse(status_code=502, content={"detalle": str(error)})


app = crear_app()
