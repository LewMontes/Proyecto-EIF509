"""Errores del dominio.

Ninguno menciona HTTP a proposito: la capa de presentacion es la unica
autorizada a traducirlos a codigos de respuesta. Asi el mismo servicio se puede
llamar desde un script o una tarea programada sin arrastrar el protocolo.

Hay dos niveles. Las **familias** (`DatosInvalidos`, `RecursoNoEncontrado`,
`ReglaDeNegocioViolada`...) son lo que la presentacion traduce: cada familia
tiene un codigo HTTP. Debajo de cada familia viven las **reglas con nombre**
(`CategoriaNoEsHoja`, `CuadreFueraDeTolerancia`...), una por regla del dominio
que puede romperse. Heredan de su familia, asi que el manejo HTTP no cambia,
pero quien atrapa la excepcion -una prueba, otro servicio, la bitacora- sabe
exactamente que regla fallo sin tener que leer el mensaje.
"""


class ErrorDeNegocio(Exception):
    """Raiz de todos los errores del dominio."""


# ---- familias ----


class DatosInvalidos(ErrorDeNegocio):
    """El dato entra con la forma correcta pero no cumple una regla del dominio."""


class RecursoNoEncontrado(ErrorDeNegocio):
    """Se referencio algo que no existe o que no pertenece al titular."""


class ReglaDeNegocioViolada(ErrorDeNegocio):
    """La operacion choca con el estado actual del sistema."""


class NoAutenticado(ErrorDeNegocio):
    """No hay una identidad valida detras de la peticion.

    Falta el token, esta vencido, su firma no calza, o la cuenta a la que
    pertenece ya no existe o esta desactivada.
    """


class AccesoDenegado(ErrorDeNegocio):
    """Quien pide esta identificado, pero no le corresponde lo que pide.

    Distinto de `NoAutenticado`: aca se sabe quien es. Lo que falla es el rol
    que la operacion exige, o que el recurso es de otra persona.
    """


class ErrorDeProveedorExterno(ErrorDeNegocio):
    """El Banco Central rechazo la solicitud del tipo de cambio, o no respondio.

    No es un error de nuestras reglas: el dato pedido era correcto, pero el
    proveedor -el servicio esta caido, la red fallo- no lo pudo resolver. Se
    distingue del resto para que la presentacion la traduzca a 502 en vez de a
    un 4xx, que sugeriria que el cliente se equivoco.
    """


# ---- datos que no cumplen una regla ----


class FechaFutura(DatosInvalidos):
    """Un gasto que todavia no ocurrio no es un gasto."""


class MontoNoPositivo(DatosInvalidos):
    """Un monto de cero o negativo no representa una compra."""


class CompraSinRenglones(DatosInvalidos):
    """Una compra sin renglones no tiene categoria ni monto."""


class DescuentoExcedido(DatosInvalidos):
    """El descuento supera el monto sobre el que se aplica."""


class TipoDeCambioRequerido(DatosInvalidos):
    """Una compra en moneda extranjera exige la tasa de su fecha; no se inventa una."""


class CorreccionVacia(DatosInvalidos):
    """Se pidio corregir una compra sin indicar que corregir."""


# ---- credenciales ----


class CredencialesInvalidas(NoAutenticado):
    """Correo o contrasena incorrectos.

    El mensaje nunca distingue cual de los dos fallo: decir «ese correo no
    existe» le confirma a quien prueba correos cuales si tienen cuenta.
    """


# ---- reglas que chocan con el estado del sistema ----


class NombreDuplicado(ReglaDeNegocioViolada):
    """Ya existe otro elemento con ese nombre dentro de la misma cuenta."""


class CorreoYaRegistrado(ReglaDeNegocioViolada):
    """Ya existe una cuenta con ese correo."""


class UsuarioInactivo(ReglaDeNegocioViolada):
    """La cuenta del titular esta desactivada."""


class CategoriaNoEsHoja(ReglaDeNegocioViolada):
    """Solo las categorias hoja reciben gasto directo; las padre totalizan."""


class CategoriaInactiva(ReglaDeNegocioViolada):
    """La categoria fue desactivada y ya no recibe gasto nuevo."""


class CategoriaConSubcategorias(ReglaDeNegocioViolada):
    """No se desactiva una categoria padre mientras tenga subcategorias activas."""


class RenglonSinCategoria(ReglaDeNegocioViolada):
    """Una compra registrada no admite renglones sin clasificar."""


class CuadreFueraDeTolerancia(ReglaDeNegocioViolada):
    """El total calculado difiere del recibo en mas de la tolerancia del dominio."""


class MetodoPagoInactivo(ReglaDeNegocioViolada):
    """El metodo de pago fue desactivado."""


class MetodoPagoAmbiguo(ReglaDeNegocioViolada):
    """Dos tarjetas del titular con los mismos ultimos cuatro digitos."""


class CampoNoAplicaAlTipo(ReglaDeNegocioViolada):
    """El dato solo tiene sentido en otro tipo de metodo de pago."""


class PrioridadDuplicada(ReglaDeNegocioViolada):
    """Dos reglas del mismo titular con la misma prioridad harian la cadena no determinista."""


class CampoDeReglaNoSoportado(ReglaDeNegocioViolada):
    """El motor todavia no evalua reglas sobre ese campo."""


class PresupuestoYaExiste(ReglaDeNegocioViolada):
    """Ya hay un presupuesto para esa categoria en ese periodo."""


class ComercioYaExiste(ReglaDeNegocioViolada):
    """Ya hay un comercio con ese nombre normalizado en el catalogo."""


class CuentaCorreoYaVinculada(ReglaDeNegocioViolada):
    """Ese buzon ya esta vinculado a la cuenta del titular."""


class CuentaCorreoInactiva(ReglaDeNegocioViolada):
    """El buzon no esta activo: no se aceptan comprobantes suyos."""


class ComprobanteDuplicado(ReglaDeNegocioViolada):
    """El buzon reentrego un mensaje que ya se habia recibido: la ingesta es idempotente."""


class TransicionDeComprobanteInvalida(ReglaDeNegocioViolada):
    """El comprobante no puede pasar del estado en que esta al que se le pide."""


class CompraYaAnulada(ReglaDeNegocioViolada):
    """Una compra anulada no se corrige ni se anula de nuevo."""
