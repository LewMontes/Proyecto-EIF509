"""Endpoint de salud. Lo usa la CI y el monitoreo para saber si la app respondio."""

from fastapi import APIRouter

from app.config.settings import obtener_configuracion
from app.presentation.schemas import SaludResponse

router = APIRouter(prefix="/api", tags=["salud"])


@router.get("/salud", response_model=SaludResponse)
def consultar_salud() -> SaludResponse:
    configuracion = obtener_configuracion()
    return SaludResponse(
        estado="OK - sistema en linea",
        aplicacion=configuracion.nombre_aplicacion,
        version=configuracion.version,
    )
