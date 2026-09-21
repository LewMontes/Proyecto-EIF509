"""Errores del dominio.

Ninguno menciona HTTP a proposito: `main.py` es el unico archivo autorizado a
traducirlos a codigos de respuesta. Asi el mismo servicio se puede llamar desde
un script o una tarea programada sin arrastrar el protocolo.
"""


class ErrorDeNegocio(Exception):
    """Raiz de todos los errores del dominio."""


class DatosInvalidos(ErrorDeNegocio):
    """El dato entra con la forma correcta pero no cumple una regla del dominio."""


class RecursoNoEncontrado(ErrorDeNegocio):
    """Se referencio algo que no existe o que no pertenece al titular."""


class ReglaDeNegocioViolada(ErrorDeNegocio):
    """La operacion choca con el estado actual del sistema."""


class ErrorDeProveedorExterno(ErrorDeNegocio):
    """El Banco Central rechazo la solicitud del tipo de cambio, o no respondio.

    No es un error de nuestras reglas: el dato pedido era correcto, pero el
    proveedor -el servicio esta caido, la red fallo- no lo pudo resolver. Se
    distingue del resto para que `main.py` la traduzca a 502 en vez de a un
    4xx, que sugeriria que el cliente se equivoco.
    """
