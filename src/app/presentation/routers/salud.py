"""Endpoint de salud. Lo usa la CI y el monitoreo para saber si la app respondio."""

from fastapi import APIRouter

from app.config.settings import get_settings
from app.presentation.schemas import SaludResponse

router = APIRouter(prefix="/api", tags=["salud"])


@router.get("/salud", response_model=SaludResponse)
def consultar_salud() -> SaludResponse:
    settings = get_settings()
    return SaludResponse(
        estado="OK - sistema en linea",
        aplicacion=settings.app_nombre,
        version=settings.app_version,
    )
