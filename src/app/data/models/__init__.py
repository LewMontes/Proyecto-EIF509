"""Entidades del dominio mapeadas a tablas.

Importa las catorce acá a propósito, aunque nadie use el paquete directamente.

SQLAlchemy resuelve las relaciones por *nombre de clase* (`relationship()` con
`"Compra"`, `"Categoria"`...), y solo encuentra los nombres de las clases que
ya se importaron alguna vez: cada `Base` recién definida se registra sola en el
registro declarativo, pero un módulo que nadie importó nunca no define nada.

Sin esta lista, qué relaciones resuelven y cuáles explotan dependería del orden
accidental en que cada punto de entrada -la app, una prueba, un script- fuera
importando modelos. Con ella, importar cualquier cosa de `app.data.models`
deja el mapeo completo y `Base.metadata` con las catorce tablas.
"""

from app.data.models.base import Base
from app.data.models.categoria import Categoria
from app.data.models.categoria_estandar import CategoriaEstandar
from app.data.models.comercio import Comercio
from app.data.models.comercio_categoria_sugerida import ComercioCategoriaSugerida
from app.data.models.compra import Compra
from app.data.models.comprobante import Comprobante
from app.data.models.cuenta_correo import CuentaCorreo
from app.data.models.linea_compra import LineaCompra
from app.data.models.metodo_pago import MetodoPago
from app.data.models.presupuesto import Presupuesto
from app.data.models.regla_categorizacion import ReglaCategorizacion
from app.data.models.tipo_cambio import TipoCambio
from app.data.models.transferencia_sinpe import TransferenciaSinpe
from app.data.models.usuario import Usuario

__all__ = [
    "Base",
    "Categoria",
    "CategoriaEstandar",
    "Comercio",
    "ComercioCategoriaSugerida",
    "Compra",
    "Comprobante",
    "CuentaCorreo",
    "LineaCompra",
    "MetodoPago",
    "Presupuesto",
    "ReglaCategorizacion",
    "TipoCambio",
    "TransferenciaSinpe",
    "Usuario",
]
