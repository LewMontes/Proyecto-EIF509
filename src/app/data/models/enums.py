"""Vocabulario cerrado del dominio.

Un enum representa un conjunto de valores que el negocio NO permite inventar
sobre la marcha. Vivir en el modelo, y no como texto libre, es lo que hace que
las reglas sobre esos valores sean verificables.

En el Laboratorio 1 solo existe el enum que usa el esqueleto. Los demas
(estados de compra, tipos de metodo de pago, estados de comprobante) se agregan
junto a sus entidades en proximos laboratorios.
"""

from enum import StrEnum


class Moneda(StrEnum):
    CRC = "CRC"
    USD = "USD"
    EUR = "EUR"
