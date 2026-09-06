"""Armado de las dependencias de cada peticion.

Es el unico lugar de la capa de presentacion que conoce a los repositorios, y
solo para inyectarlos: los routers reciben el servicio ya construido y nunca
tocan la base directamente.
"""

from typing import Annotated

import httpx
from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.business.errors import AccesoDenegado, CredencialesInvalidas
from app.business.services.auth_service import AuthService
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.categoria_service import CategoriaService
from app.business.services.comercio_service import ComercioService
from app.business.services.compra_service import CompraService
from app.business.services.conciliacion_service import ConciliacionService
from app.business.services.correo.gmail import GmailProveedor
from app.business.services.correo.outlook import OutlookProveedor
from app.business.services.correo.proveedor import ProveedorDeCorreo
from app.business.services.cuenta_correo_service import CuentaCorreoService
from app.business.services.identidad_google import IdentidadGoogleProveedor
from app.business.services.metodo_pago_service import MetodoPagoService
from app.business.services.presupuesto_service import PresupuestoService
from app.business.services.regla_categorizacion_service import ReglaCategorizacionService
from app.business.services.tipo_cambio_service import TipoCambioService
from app.config.cliente_http import obtener_cliente_http
from app.config.cliente_mongo import obtener_coleccion_bitacora
from app.config.database import obtener_sesion
from app.config.settings import obtener_configuracion
from app.data.models.enums import ProveedorCorreo
from app.data.models.usuario import Usuario
from app.data.repositories.bitacora_repository import BitacoraRepository
from app.data.repositories.categoria_estandar_repository import CategoriaEstandarRepository
from app.data.repositories.categoria_repository import CategoriaRepository
from app.data.repositories.comercio_categoria_repository import ComercioCategoriaRepository
from app.data.repositories.comercio_repository import ComercioRepository
from app.data.repositories.compra_repository import CompraRepository
from app.data.repositories.comprobante_repository import ComprobanteRepository
from app.data.repositories.cuenta_correo_repository import CuentaCorreoRepository
from app.data.repositories.linea_compra_repository import LineaCompraRepository
from app.data.repositories.metodo_pago_repository import MetodoPagoRepository
from app.data.repositories.presupuesto_repository import PresupuestoRepository
from app.data.repositories.regla_categorizacion_repository import ReglaCategorizacionRepository
from app.data.repositories.tipo_cambio_repository import TipoCambioRepository
from app.data.repositories.transferencia_sinpe_repository import TransferenciaSinpeRepository
from app.data.repositories.usuario_repository import UsuarioRepository

SesionDependencia = Annotated[Session, Depends(obtener_sesion)]
ClienteHttpDependencia = Annotated[httpx.Client, Depends(obtener_cliente_http)]


def obtener_servicio_de_categorias(sesion: SesionDependencia) -> CategoriaService:
    """Arma el servicio de categorias con sus repositorios sobre la sesion actual."""
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


ServicioDeCategorias = Annotated[CategoriaService, Depends(obtener_servicio_de_categorias)]


def obtener_proveedores_de_correo(
    cliente: ClienteHttpDependencia,
) -> dict[ProveedorCorreo, ProveedorDeCorreo]:
    """Arma un proveedor por cada correo que el sistema sabe vincular."""
    configuracion = obtener_configuracion()
    return {
        ProveedorCorreo.OUTLOOK: OutlookProveedor(cliente, configuracion),
        ProveedorCorreo.GMAIL: GmailProveedor(cliente, configuracion),
    }


ProveedoresDeCorreoDependencia = Annotated[
    dict[ProveedorCorreo, ProveedorDeCorreo], Depends(obtener_proveedores_de_correo)
]


def obtener_servicio_de_cuentas_correo(
    sesion: SesionDependencia,
    proveedores: ProveedoresDeCorreoDependencia,
    cliente: ClienteHttpDependencia,
) -> CuentaCorreoService:
    """Arma el servicio de cuentas de correo con sus repositorios y proveedores.

    Recibe también el servicio de tipo de cambio, pero no para convertir nada:
    lo usa para sellar cada comprobante nuevo con la tasa del día en que se
    sincroniza, y así poder convertirlo después sin depender de una consulta
    histórica al Banco Central. Y el servicio de conciliación, que corre justo
    después de guardar cada comprobante nuevo -ver `ConciliacionService`.
    """
    return CuentaCorreoService(
        CuentaCorreoRepository(sesion),
        UsuarioRepository(sesion),
        proveedores,
        ComprobanteRepository(sesion),
        TransferenciaSinpeRepository(sesion),
        obtener_servicio_de_tipo_cambio(cliente),
        obtener_servicio_de_conciliacion(sesion, cliente),
    )


ServicioDeCuentasCorreo = Annotated[
    CuentaCorreoService, Depends(obtener_servicio_de_cuentas_correo)
]


def obtener_servicio_de_comercios(sesion: SesionDependencia) -> ComercioService:
    """Arma el servicio de comercios con sus repositorios sobre la sesion actual."""
    return ComercioService(
        ComercioRepository(sesion),
        ComercioCategoriaRepository(sesion),
        CategoriaRepository(sesion),
    )


ServicioDeComercios = Annotated[ComercioService, Depends(obtener_servicio_de_comercios)]


def obtener_servicio_de_presupuestos(sesion: SesionDependencia) -> PresupuestoService:
    """Arma el servicio de presupuestos con sus repositorios sobre la sesion actual."""
    return PresupuestoService(
        PresupuestoRepository(sesion), CategoriaRepository(sesion), UsuarioRepository(sesion)
    )


ServicioDePresupuestos = Annotated[PresupuestoService, Depends(obtener_servicio_de_presupuestos)]


def obtener_servicio_de_metodos_pago(sesion: SesionDependencia) -> MetodoPagoService:
    """Arma el servicio de métodos de pago con sus repositorios sobre la sesion actual."""
    return MetodoPagoService(MetodoPagoRepository(sesion), UsuarioRepository(sesion))


ServicioDeMetodosPago = Annotated[MetodoPagoService, Depends(obtener_servicio_de_metodos_pago)]


def obtener_servicio_de_compras(sesion: SesionDependencia) -> CompraService:
    """Arma el servicio de lectura de compras sobre la sesion actual.

    Le basta el repositorio de `Compra`: los nombres que la lista y el detalle
    muestran -comercio, método de pago, categoría- llegan por las relaciones
    que ese repositorio carga en la misma consulta. Antes recibía cinco
    repositorios más, uno por cada id que el servicio resolvía a mano.
    """
    return CompraService(CompraRepository(sesion))


ServicioDeCompras = Annotated[CompraService, Depends(obtener_servicio_de_compras)]


def obtener_servicio_de_reglas_categorizacion(
    sesion: SesionDependencia,
) -> ReglaCategorizacionService:
    """Arma el servicio de reglas de categorización con sus repositorios sobre la sesion actual."""
    return ReglaCategorizacionService(
        ReglaCategorizacionRepository(sesion),
        CategoriaRepository(sesion),
        UsuarioRepository(sesion),
    )


ServicioDeReglasCategorizacion = Annotated[
    ReglaCategorizacionService, Depends(obtener_servicio_de_reglas_categorizacion)
]


def obtener_servicio_de_bitacora() -> BitacoraComprasService:
    """Arma el servicio de bitácora sobre la colección de Mongo compartida.

    `obtener_coleccion_bitacora()` nunca falla por sí sola -la conexión es
    perezosa- así que este servicio siempre se puede construir, incluso si
    Mongo termina no respondiendo cuando de verdad se intenta escribir.
    """
    return BitacoraComprasService(BitacoraRepository(obtener_coleccion_bitacora()))


ServicioDeBitacora = Annotated[BitacoraComprasService, Depends(obtener_servicio_de_bitacora)]


def obtener_servicio_de_conciliacion(
    sesion: SesionDependencia, cliente: ClienteHttpDependencia
) -> ConciliacionService:
    """Arma el servicio de conciliación con todos los repositorios que el
    Proceso 2 necesita tocar en su transacción, más el servicio de comercios
    (catálogo compartido) y el de tipo de cambio (opcional, igual que en
    `CuentaCorreoService`)."""
    return ConciliacionService(
        CompraRepository(sesion),
        LineaCompraRepository(sesion),
        MetodoPagoRepository(sesion),
        ReglaCategorizacionRepository(sesion),
        PresupuestoRepository(sesion),
        CategoriaRepository(sesion),
        ComercioCategoriaRepository(sesion),
        TipoCambioRepository(sesion),
        ComprobanteRepository(sesion),
        obtener_servicio_de_comercios(sesion),
        obtener_servicio_de_tipo_cambio(cliente),
        obtener_servicio_de_bitacora(),
    )


ServicioDeConciliacion = Annotated[ConciliacionService, Depends(obtener_servicio_de_conciliacion)]


_servicio_de_tipo_cambio: TipoCambioService | None = None


def obtener_servicio_de_tipo_cambio(cliente: ClienteHttpDependencia) -> TipoCambioService:
    """Arma (una sola vez) el servicio de tipo de cambio, con su caché por fecha.

    A diferencia de los demás servicios, este no depende de la sesion de
    base de datos -no persiste nada por usuario- así que es el único que
    conviene reutilizar entre peticiones en vez de armar de cero cada vez:
    su caché en memoria solo sirve si sobrevive más de una petición.
    """
    global _servicio_de_tipo_cambio
    if _servicio_de_tipo_cambio is None:
        _servicio_de_tipo_cambio = TipoCambioService(cliente, obtener_configuracion())
    return _servicio_de_tipo_cambio


ServicioDeTipoCambio = Annotated[TipoCambioService, Depends(obtener_servicio_de_tipo_cambio)]


def obtener_servicio_de_auth(
    sesion: SesionDependencia, cliente: ClienteHttpDependencia
) -> AuthService:
    """Arma el servicio de autenticación sobre la sesion actual.

    El proveedor de Google queda en `None` -y "Iniciar sesión con Google"
    da un error claro en vez de arrancar mal- si no hay credenciales de
    Google configuradas; mismo criterio que Outlook/Gmail para leer correo.

    Recibe también el servicio de categorías, para sembrar la jerarquía
    estándar de todo titular nuevo justo al registrarse -ver
    `CategoriaService.sembrar_estandar`.
    """
    configuracion = obtener_configuracion()
    google = (
        IdentidadGoogleProveedor(cliente, configuracion) if configuracion.google_client_id else None
    )
    return AuthService(UsuarioRepository(sesion), google, obtener_servicio_de_categorias(sesion))


ServicioDeAuth = Annotated[AuthService, Depends(obtener_servicio_de_auth)]


def obtener_usuario_actual(
    servicio: ServicioDeAuth,
    autorizacion: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Usuario:
    """Resuelve el titular autenticado a partir del encabezado `Authorization: Bearer <token>`.

    Es la base de todo lo demás en este archivo relacionado con permisos: un
    endpoint que dependa de esto exige sesión iniciada, y uno que además use
    `VerificarTitular` exige que esa sesión sea la del `usuario_id` que se le
    está pidiendo.
    """
    if autorizacion is None or not autorizacion.startswith("Bearer "):
        raise CredencialesInvalidas("Falta iniciar sesión.")
    return servicio.usuario_de_token(autorizacion.removeprefix("Bearer "))


UsuarioActualDependencia = Annotated[Usuario, Depends(obtener_usuario_actual)]


def verificar_titular(
    usuario_actual: UsuarioActualDependencia,
    # Las mismas cotas que cada endpoint ya declara en su propio
    # `usuario_id: int = Query(gt=0, le=2_147_483_647)` -no alcanza con que
    # una de las dos declaraciones las tenga: FastAPI valida cada una contra
    # el valor crudo por separado, y esta corre antes de que la del endpoint
    # tenga oportunidad. Sin las mismas cotas acá, un id fuera de rango
    # pasaba esta validación (sin bordes) y llegaba al cuerpo de la función,
    # que lo comparaba contra `usuario_actual.id` y siempre daba 403 -un id
    # mal formado terminaba pareciendo "no sos el dueño" en vez de "esto no
    # es un id válido".
    usuario_id: int = Query(gt=0, le=2_147_483_647),
) -> None:
    """Confirma que el titular autenticado es el mismo `usuario_id` que la petición pide.

    La API siempre recibió `usuario_id` explícito en la URL -eso no cambia
    acá- pero antes de esto nada impedía pedir los datos de cualquier otro
    con solo cambiar el número: no había forma de estar "autenticado como"
    nadie.
    """
    if usuario_actual.id != usuario_id:
        raise AccesoDenegado("No podés acceder a los datos de otro titular.")


VerificarTitular = Annotated[None, Depends(verificar_titular)]


def verificar_mismo_usuario(usuario_actual: Usuario, usuario_id_declarado: int) -> None:
    """Lo mismo que `verificar_titular`, para los pocos endpoints donde `usuario_id`
    viaja en el cuerpo del pedido en vez de en la URL -ahí no hay un parámetro
    de query que compartir, así que se llama explícitamente con el valor ya
    parseado del cuerpo.
    """
    if usuario_actual.id != usuario_id_declarado:
        raise AccesoDenegado("No podés acceder a los datos de otro titular.")
