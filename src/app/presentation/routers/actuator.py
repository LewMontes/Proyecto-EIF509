"""`/actuator/health`: el equivalente del health check de Spring Boot Actuator.

Lo consulta la plataforma de despliegue para saber si la instancia puede
recibir tráfico, el `HEALTHCHECK` del contenedor y el paso final del pipeline
después de desplegar.

Difiere de `/api/salud` en lo que importa para eso: **pregunta a la base**. Una
app que arrancó pero perdió su PostgreSQL está viva y no sirve; `/api/salud`
diría que sí, este endpoint responde `503 DOWN` y la plataforma deja de
mandarle tráfico.

**Sin detalles**, como `management.endpoint.health.show-details=never`: solo
`{"status": "UP"}` o `{"status": "DOWN"}`. Es público -quien pregunta todavía
no es nadie- y por eso mismo no dice qué base hay detrás, qué versión corre ni
por qué falló. El porqué queda en el registro del servidor.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.presentation.dependencies import SesionDependencia

registro = logging.getLogger("gastonomo.salud")

router = APIRouter(prefix="/actuator", tags=["salud"])


@router.get(
    "/health",
    summary="Si la instancia puede atender: la app responde y su base también",
    responses={
        200: {"content": {"application/json": {"example": {"status": "UP"}}}},
        503: {"content": {"application/json": {"example": {"status": "DOWN"}}}},
    },
)
def health(sesion: SesionDependencia) -> JSONResponse:
    try:
        sesion.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001 -cualquier fallo de la base es DOWN
        registro.error(
            "La base de datos no responde al health check",
            exc_info=error,
            extra={"evento": "salud_caida"},
        )
        return JSONResponse(status_code=503, content={"status": "DOWN"})
    return JSONResponse(content={"status": "UP"})
