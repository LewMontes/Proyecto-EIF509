"""Endpoint de salud. Lo usa la CI y el monitoreo para saber si la app respondio.

Es el unico que vive fuera de `/api/v1` y sin token, y las dos cosas son a
proposito: no es parte del contrato de negocio que se versiona -un balanceador
o el paso de la CI le pegan siempre a la misma ruta, exista la version que
exista- y quien pregunta si la aplicacion esta viva todavia no es nadie.
"""

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
