"""Punto de entrada de la aplicacion.

Arranca con:  uvicorn app.main:app --reload --app-dir src
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.business.errors import RecursoNoEncontrado, ReglaDeNegocioViolada, ValidacionFallida
from app.config.database import crear_tablas
from app.config.settings import get_settings
from app.presentation.routers import categorias, salud


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    """Prepara la base al arrancar. Mas adelante lo reemplazan las migraciones."""
    crear_tablas()
    yield


def crear_app() -> FastAPI:
    """Fabrica de la aplicacion.

    Se usa una funcion en vez de un app global para poder crear instancias
    limpias en las pruebas sin arrastrar configuracion de una a otra.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_nombre,
        version=settings.app_version,
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
    app.include_router(categorias.router)

    registrar_manejadores_de_error(app)
    return app


def registrar_manejadores_de_error(app: FastAPI) -> None:
    """Traduce los errores de negocio a codigos HTTP.

    Esta traduccion es responsabilidad de la capa de presentacion: es el unico
    lugar del sistema al que se le permite saber que existen los codigos HTTP.
    """

    @app.exception_handler(ValidacionFallida)
    def _validacion(_: Request, error: ValidacionFallida) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detalle": str(error)})

    @app.exception_handler(ReglaDeNegocioViolada)
    def _regla(_: Request, error: ReglaDeNegocioViolada) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detalle": str(error)})

    @app.exception_handler(RecursoNoEncontrado)
    def _no_encontrado(_: Request, error: RecursoNoEncontrado) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detalle": str(error)})


app = crear_app()
