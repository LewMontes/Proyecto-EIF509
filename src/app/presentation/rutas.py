"""La versión del contrato, en un solo lugar.

La versión va en la ruta (`/api/v1/...`) y no en un encabezado: se ve en
cualquier registro de acceso, se puede probar pegando la URL en el navegador, y
deja convivir a `/api/v1` con una futura `/api/v2` como dos árboles de rutas
distintos mientras los clientes migran.

Cada router arma su prefijo a partir de esta constante, así que el día que
exista una `v2` el cambio no es buscar y reemplazar una cadena en diez archivos.
"""

API_V1 = "/api/v1"


def ubicacion(recurso: str, identificador: int) -> str:
    """La URL del recurso recién creado, para el encabezado `Location` de un 201."""
    return f"{API_V1}/{recurso}/{identificador}"
