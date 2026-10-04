"""Armado de las dependencias de cada peticion.

Es el unico lugar de la capa de presentacion que conoce a los repositorios, y
solo para inyectarlos: los routers reciben el servicio ya construido y nunca
tocan la base directamente.

Cada dependencia arma su servicio con los repositorios que necesita, sobre la
sesion de ESTA peticion. La sesion vive lo que dura la peticion y se cierra
siempre -`obtener_sesion` lo garantiza con su `finally`- asi que dos peticiones
simultaneas nunca comparten estado de SQLAlchemy.

Aca vive tambien la **cadena de seguridad** de la API, que es el equivalente de
un `SecurityFilterChain` stateless: `obtener_usuario_actual` saca el token del
encabezado `Authorization` y lo convierte en una identidad, y `exigir_rol`
autoriza por rol. No hay sesion de servidor ni cookie: cada peticion se
autentica sola, con su propio token.
"""

from collections.abc import Callable
from typing import Annotated

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.business.errors import AccesoDenegado, NoAutenticado
from app.business.services.auth_service import AuthService, UsuarioAutenticado
from app.business.services.bitacora_service import BitacoraComprasService
from app.business.services.categoria_service import CategoriaService
from app.business.services.comercio_service import ComercioService
from app.business.services.compra_service import CompraService
from app.business.services.comprobante_service import ComprobanteService
from app.business.services.conciliacion_service import ConciliacionService
from app.business.services.cuenta_correo_service import CuentaCorreoService
from app.business.services.metodo_pago_service import MetodoPagoService
from app.business.services.presupuesto_service import PresupuestoService
from app.business.services.registrar_compra_service import RegistrarCompraService
from app.business.services.regla_categorizacion_service import ReglaCategorizacionService
from app.business.services.tipo_cambio_service import TipoCambioService
from app.business.services.usuario_service import UsuarioService
from app.config.cliente_http import obtener_cliente_http
from app.config.cliente_mongo import marcar_mongo_caido, obtener_coleccion_bitacora
from app.config.database import obtener_sesion
from app.config.settings import obtener_configuracion
from app.data.models.enums import RolUsuario
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
from app.data.repositories.usuario_repository import UsuarioRepository

SesionDependencia = Annotated[Session, Depends(obtener_sesion)]
ClienteHttpDependencia = Annotated[httpx.Client, Depends(obtener_cliente_http)]


# ---- seguridad ----


def obtener_servicio_de_auth(sesion: SesionDependencia) -> AuthService:
    """Arma el servicio de autenticacion con la clave de firma del ambiente."""
    configuracion = obtener_configuracion()
    return AuthService(
        UsuarioRepository(sesion), configuracion.jwt_secreto, configuracion.jwt_minutos
    )


ServicioDeAuth = Annotated[AuthService, Depends(obtener_servicio_de_auth)]

# `auto_error=False`: sin token, FastAPI no responde por su cuenta -deja que
# `obtener_usuario_actual` lance `NoAutenticado`, para que el 401 salga con la
# misma forma que el resto de los errores de la API. Declarar el esquema aca es
# ademas lo que le pone el boton «Authorize» a Swagger UI.
_esquema_bearer = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description="El `access_token` que devuelve `POST /api/v1/auth/login`.",
)
CredencialesBearer = Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)]


def obtener_usuario_actual(
    credenciales: CredencialesBearer, servicio: ServicioDeAuth
) -> UsuarioAutenticado:
    """La identidad detras de la peticion, a partir de `Authorization: Bearer <token>`.

    Todo endpoint protegido depende de esto, y de aca sale el `usuario_id` de
    cada operacion: ningun endpoint lo acepta del cuerpo ni de la URL.
    """
    if credenciales is None:
        raise NoAutenticado("Falta el token de acceso: iniciá sesión en /api/v1/auth/login.")
    return servicio.usuario_de_token(credenciales.credentials)


UsuarioActual = Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)]


def exigir_rol(*roles: RolUsuario) -> Callable[[UsuarioAutenticado], UsuarioAutenticado]:
    """Autorizacion por endpoint: deja pasar solo a quien tenga uno de esos roles.

    Se usa como dependencia del endpoint -`Depends(exigir_rol(RolUsuario.ADMIN))`-,
    asi que el rol que exige cada ruta queda escrito al lado de la ruta. Primero
    autentica (401 si no hay identidad) y recien despues autoriza (403 si la
    identidad no alcanza): son dos preguntas distintas con dos respuestas
    distintas.
    """

    def _verificar(usuario: UsuarioActual) -> UsuarioAutenticado:
        if usuario.rol not in roles:
            permitidos = ", ".join(rol.value for rol in roles)
            raise AccesoDenegado(f"Esta operación exige el rol {permitidos}.")
        return usuario

    return _verificar


Administrador = Annotated[UsuarioAutenticado, Depends(exigir_rol(RolUsuario.ADMIN))]


# ---- servicios ----


def obtener_servicio_de_categorias(sesion: SesionDependencia) -> CategoriaService:
    """Arma el servicio de categorias con sus repositorios sobre la sesion actual.

    Necesita tres: el de categorias para las suyas, el de titulares para
    comprobar que quien pide exista y este activo, y el del catalogo estandar
    para sembrar la jerarquia inicial de una cuenta nueva.
    """
    return CategoriaService(
        CategoriaRepository(sesion), UsuarioRepository(sesion), CategoriaEstandarRepository(sesion)
    )


ServicioDeCategorias = Annotated[CategoriaService, Depends(obtener_servicio_de_categorias)]


def obtener_servicio_de_usuarios(sesion: SesionDependencia) -> UsuarioService:
    """Arma el servicio de cuentas, con el de categorias para sembrar la jerarquia inicial."""
    return UsuarioService(UsuarioRepository(sesion), obtener_servicio_de_categorias(sesion))


ServicioDeUsuarios = Annotated[UsuarioService, Depends(obtener_servicio_de_usuarios)]


def obtener_servicio_de_comercios(sesion: SesionDependencia) -> ComercioService:
    """Arma el servicio del catalogo compartido de comercios."""
    return ComercioService(
        ComercioRepository(sesion),
        ComercioCategoriaRepository(sesion),
        CategoriaRepository(sesion),
    )


ServicioDeComercios = Annotated[ComercioService, Depends(obtener_servicio_de_comercios)]


def obtener_servicio_de_metodos_pago(sesion: SesionDependencia) -> MetodoPagoService:
    """Arma el servicio de metodos de pago sobre la sesion actual."""
    return MetodoPagoService(MetodoPagoRepository(sesion), UsuarioRepository(sesion))


ServicioDeMetodosPago = Annotated[MetodoPagoService, Depends(obtener_servicio_de_metodos_pago)]


def obtener_servicio_de_presupuestos(sesion: SesionDependencia) -> PresupuestoService:
    """Arma el servicio de presupuestos sobre la sesion actual."""
    return PresupuestoService(
        PresupuestoRepository(sesion), CategoriaRepository(sesion), UsuarioRepository(sesion)
    )


ServicioDePresupuestos = Annotated[PresupuestoService, Depends(obtener_servicio_de_presupuestos)]


def obtener_servicio_de_reglas_categorizacion(
    sesion: SesionDependencia,
) -> ReglaCategorizacionService:
    """Arma el servicio de reglas de categorizacion sobre la sesion actual."""
    return ReglaCategorizacionService(
        ReglaCategorizacionRepository(sesion),
        CategoriaRepository(sesion),
        UsuarioRepository(sesion),
    )


ServicioDeReglasCategorizacion = Annotated[
    ReglaCategorizacionService, Depends(obtener_servicio_de_reglas_categorizacion)
]


def obtener_servicio_de_compras(sesion: SesionDependencia) -> CompraService:
    """Arma el servicio de lectura de compras sobre la sesion actual.

    Le basta el repositorio de `Compra`: los nombres que la lista y el detalle
    muestran -comercio, metodo de pago, categoria- llegan por las relaciones
    que ese repositorio carga en la misma consulta, no por un repositorio
    aparte para cada uno. Ver docs/persistencia.md, seccion 5.
    """
    return CompraService(CompraRepository(sesion))


ServicioDeCompras = Annotated[CompraService, Depends(obtener_servicio_de_compras)]


def obtener_servicio_de_bitacora() -> BitacoraComprasService:
    """Arma el servicio de bitacora sobre la coleccion de Mongo compartida.

    No recibe la sesion de SQLAlchemy: la bitacora vive en Mongo, no en
    PostgreSQL, y no participa de la transaccion de negocio (ver ADR-002).

    Este servicio siempre se puede construir, este Mongo arriba o no. Si no
    respondio hace poco, `obtener_coleccion_bitacora()` devuelve `None` y la
    bitacora es un no-op; si deja de responder a mitad de la peticion, lo
    absorbe `BitacoraRepository`, que deja de intentar y avisa por
    `marcar_mongo_caido` para que las peticiones siguientes no vuelvan a
    esperarlo.
    """
    return BitacoraComprasService(
        BitacoraRepository(obtener_coleccion_bitacora(), al_fallar=marcar_mongo_caido)
    )


ServicioDeBitacora = Annotated[BitacoraComprasService, Depends(obtener_servicio_de_bitacora)]


_servicio_de_tipo_cambio: TipoCambioService | None = None


def obtener_servicio_de_tipo_cambio(cliente: ClienteHttpDependencia) -> TipoCambioService:
    """Arma (una sola vez) el servicio de tipo de cambio, con su cache por fecha.

    A diferencia de los demas, este no depende de la sesion de base de datos
    -no persiste nada por titular- asi que es el unico que conviene reutilizar
    entre peticiones en vez de armar de cero cada vez: su cache en memoria solo
    sirve si sobrevive mas de una peticion.
    """
    global _servicio_de_tipo_cambio
    if _servicio_de_tipo_cambio is None:
        _servicio_de_tipo_cambio = TipoCambioService(cliente, obtener_configuracion())
    return _servicio_de_tipo_cambio


ServicioDeTipoCambio = Annotated[TipoCambioService, Depends(obtener_servicio_de_tipo_cambio)]


def obtener_servicio_de_conciliacion(
    sesion: SesionDependencia,
    tipo_cambio: ServicioDeTipoCambio,
    bitacora: ServicioDeBitacora,
) -> ConciliacionService:
    """Arma el Proceso 2 con todos los repositorios que su transaccion toca.

    Son cinco tablas -`compra`, `linea_compra`, `regla_categorizacion`,
    `presupuesto` y `comprobante`- mas el servicio de comercios, que resuelve
    el catalogo compartido y confirma aparte a proposito, y el de tipo de
    cambio, que solo entra cuando la moneda no es la base.

    El tipo de cambio y la bitacora llegan como dependencias -no se arman aca
    adentro- para que una prueba pueda reemplazarlos con
    `dependency_overrides` sin tocar la red ni Mongo.
    """
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
        tipo_cambio,
        bitacora,
    )


ServicioDeConciliacion = Annotated[ConciliacionService, Depends(obtener_servicio_de_conciliacion)]


def obtener_servicio_de_cuentas_correo(sesion: SesionDependencia) -> CuentaCorreoService:
    """Arma el servicio de los buzones del titular."""
    return CuentaCorreoService(CuentaCorreoRepository(sesion), UsuarioRepository(sesion))


ServicioDeCuentasCorreo = Annotated[
    CuentaCorreoService, Depends(obtener_servicio_de_cuentas_correo)
]


def obtener_servicio_de_comprobantes(
    sesion: SesionDependencia, conciliacion: ServicioDeConciliacion
) -> ComprobanteService:
    """Arma la ingesta: es lo que conecta el Proceso 2 con la API.

    Recibe el servicio de conciliacion ya armado sobre la MISMA sesion: la
    constancia del comprobante y la conciliacion que la sigue tienen que ver
    las mismas filas.
    """
    return ComprobanteService(
        ComprobanteRepository(sesion), CuentaCorreoRepository(sesion), conciliacion
    )


ServicioDeComprobantes = Annotated[ComprobanteService, Depends(obtener_servicio_de_comprobantes)]


def obtener_servicio_de_registro_de_compras(
    sesion: SesionDependencia, bitacora: ServicioDeBitacora
) -> RegistrarCompraService:
    """Arma el Proceso 1 -la captura manual con desglose.

    No recibe el servicio de tipo de cambio, a diferencia de la conciliacion:
    la tasa de una compra capturada a mano llega en el propio comando, porque
    el titular puede estar registrando una compra de hace meses y la tasa de
    hoy no es la que pago.
    """
    return RegistrarCompraService(
        CompraRepository(sesion),
        LineaCompraRepository(sesion),
        CategoriaRepository(sesion),
        MetodoPagoRepository(sesion),
        PresupuestoRepository(sesion),
        ReglaCategorizacionRepository(sesion),
        UsuarioRepository(sesion),
        obtener_servicio_de_comercios(sesion),
        bitacora,
    )


ServicioDeRegistroDeCompras = Annotated[
    RegistrarCompraService, Depends(obtener_servicio_de_registro_de_compras)
]
