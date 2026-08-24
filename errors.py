"""Errores de negocio.

Son distintos de los errores HTTP a proposito: la capa de negocio no sabe que
existe HTTP. Es la capa de presentacion la que traduce cada uno de estos a su
codigo de respuesta correspondiente.
"""


class ErrorDeNegocio(Exception):
    """Base de todas las violaciones de reglas del dominio."""


class ReglaDeNegocioViolada(ErrorDeNegocio):
    """Se intento algo que el negocio no permite."""


class ValidacionFallida(ErrorDeNegocio):
    """Los datos no cumplen una condicion necesaria para continuar."""


class RecursoNoEncontrado(ErrorDeNegocio):
    """Se referencio una entidad que no existe o no pertenece al usuario."""
