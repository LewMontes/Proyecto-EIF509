"""Cliente HTTP compartido para hablar con Microsoft Graph y la API de Google.

Un solo `httpx.Client` para toda la aplicación reutiliza sus conexiones TCP en
vez de abrir una por petición, igual que el motor de base de datos es uno solo
para toda la app. Se cierra en el `lifespan` de `main.py` cuando el servidor
apaga.
"""

import httpx

_cliente: httpx.Client | None = None


def obtener_cliente_http() -> httpx.Client:
    """Entrega el cliente HTTP compartido, creándolo la primera vez que se pide."""
    global _cliente
    if _cliente is None:
        _cliente = httpx.Client(timeout=10.0)
    return _cliente


def cerrar_cliente_http() -> None:
    """Cierra el cliente compartido. Se llama al apagar la aplicación."""
    global _cliente
    if _cliente is not None:
        _cliente.close()
        _cliente = None
