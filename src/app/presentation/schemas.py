"""DTOs de entrada y salida de la API.

Viven en presentacion, no en negocio: describen el contrato HTTP y pueden
cambiar sin que el dominio se entere.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.data.models.enums import (
    CampoRegla,
    EstadoCompra,
    EstadoCuentaCorreo,
    EstadoPresupuesto,
    Moneda,
    OrigenCompra,
    ProveedorCorreo,
    TipoMetodoPago,
)

# Tope real de una columna INTEGER de PostgreSQL. Un id "válido" (positivo)
# pero absurdamente grande pasa `gt=0` sin problema y solo revienta al
# convertirlo al tipo real de la columna -sqlalchemy.exc.DataError bajo
# PostgreSQL, un OverflowError crudo de Python bajo SQLite. Ponerle este
# techo acá, y no solo confiar en el manejador de errores de main.py, da un
# 422 con mensaje consistente sin importar qué motor esté detrás.
_ID_MAXIMO = 2_147_483_647


class SaludResponse(BaseModel):
    """Respuesta del endpoint de salud."""

    estado: str
    aplicacion: str
    version: str


class RegistrarUsuarioRequest(BaseModel):
    """Cuerpo de POST /api/auth/registro."""

    nombre_completo: str = Field(min_length=1, max_length=120)
    correo: str = Field(min_length=3, max_length=180)
    # El mínimo real (8 caracteres) lo aplica AuthService, no acá: es una
    # regla de negocio -puede cambiar sin tocar el contrato HTTP- y no una
    # restricción de forma del dato. Este máximo sí es de forma: bcrypt trunca
    # en 72 bytes, así que una contraseña más larga que eso simplemente
    # perdería los caracteres de más sin que nadie se entere.
    contrasena: str = Field(min_length=1, max_length=72)


class IniciarSesionRequest(BaseModel):
    """Cuerpo de POST /api/auth/iniciar-sesion."""

    correo: str = Field(min_length=1, max_length=180)
    contrasena: str = Field(min_length=1, max_length=72)


class UrlDeAutorizacionResponse(BaseModel):
    """La URL de Google a la que el frontend debe redirigir al titular."""

    url_autorizacion: str


class CallbackGoogleRequest(BaseModel):
    """Cuerpo que manda el frontend tras volver de Google -tanto para iniciar sesión
    como para vincular Google a una cuenta ya logueada. `codigo` y `estado` son
    justamente el `code` y el `state` que Google agregó a la URL de retorno."""

    codigo: str = Field(min_length=1)
    estado: str = Field(min_length=1)


class CambiarContrasenaRequest(BaseModel):
    """Cuerpo de POST /api/auth/contrasena.

    `contrasena_actual` es opcional en la forma del dato -una cuenta que
    llegó solo por Google todavía no tiene ninguna que confirmar- pero
    `AuthService.cambiar_contrasena` sí la exige si el titular ya tenía una.
    """

    contrasena_actual: str | None = Field(default=None, max_length=72)
    contrasena_nueva: str = Field(min_length=1, max_length=72)


class UsuarioResponse(BaseModel):
    """El titular autenticado, sin su hash de contraseña.

    `tiene_contrasena` y `google_vinculado` no son columnas de `Usuario`, son
    derivadas (`contrasena_hash`/`google_id` no nulos) -por eso este modelo
    no sale de un `model_validate(usuario)` directo, sino de un pequeño
    constructor en el router (`_respuesta_de_usuario`). Ajustes los usa para
    saber si mostrar "Poné una contraseña" o "Cambiar contraseña", y si
    "Vincular Google" o "Desvincular Google".
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_completo: str
    correo: str
    moneda_preferida: Moneda
    tiene_contrasena: bool
    google_vinculado: bool
    leer_transferencias_sinpe: bool


class PreferenciaSinpeRequest(BaseModel):
    """Cuerpo de POST /api/auth/preferencias/sinpe."""

    activo: bool


class SesionResponse(BaseModel):
    """Lo que devuelve registrarse o iniciar sesión: el token y quién es."""

    token: str
    usuario: UsuarioResponse


class CrearCategoriaRequest(BaseModel):
    """Cuerpo de POST /api/categorias.

    Solo valida la forma del dato (tipos, largos, formato). Si la categoria se
    puede crear o no es una pregunta del negocio, y se responde en el servicio.
    """

    usuario_id: int = Field(gt=0, le=_ID_MAXIMO, description="Titular dueno de la categoria")
    nombre: str = Field(min_length=1, max_length=60, examples=["Alimentacion"])
    color_hex: str = Field(max_length=7, examples=["#2563EB"])
    descripcion: str | None = Field(default=None, max_length=255)
    categoria_padre_id: int | None = Field(
        default=None,
        gt=0,
        le=_ID_MAXIMO,
        description="Categoria que la totaliza, si es subcategoria",
    )


class CategoriaResponse(BaseModel):
    """Categoria tal como la ve el cliente."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    nombre: str
    descripcion: str | None
    color_hex: str
    categoria_padre_id: int | None
    es_hoja: bool
    activa: bool


class ErrorResponse(BaseModel):
    """Forma unica de los errores de negocio traducidos a HTTP."""

    detalle: str


class IniciarVinculacionResponse(BaseModel):
    """URL a la que el frontend debe redirigir al titular para autorizar el acceso."""

    url_autorizacion: str


class CuentaCorreoResponse(BaseModel):
    """Una cuenta de correo vinculada, sin ningun dato de token."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    proveedor: ProveedorCorreo
    direccion: str
    estado: EstadoCuentaCorreo
    ultima_sincronizacion: datetime | None


class MensajeResumidoResponse(BaseModel):
    """Metadatos de un mensaje reciente, usados solo para probar la conexion."""

    identificador: str
    remitente: str
    asunto: str
    recibido_en: datetime | None


class ComprobanteParseadoResponse(BaseModel):
    """Lo que el parser de BAC logró leer del cuerpo de un mensaje.

    Todavía no es una `Compra`: es la lectura cruda, previa a resolver el
    comercio, emparejar el método de pago y persistir nada.
    """

    model_config = ConfigDict(from_attributes=True)

    banco: str
    comercio: str | None
    ciudad: str | None
    pais: str | None
    fecha: datetime | None
    marca_tarjeta: str | None
    ultimos_cuatro: str | None
    autorizacion: str | None
    referencia: str | None
    tipo_transaccion: str | None
    moneda: str | None
    monto: Decimal | None
    confianza: float
    es_compra: bool
    es_confiable: bool


class ResumenMensualResponse(BaseModel):
    """Total de compras de un mes, en una moneda."""

    model_config = ConfigDict(from_attributes=True)

    anio: int
    mes: int
    moneda: str
    total: Decimal
    cantidad_transacciones: int


class TipoDeCambioResponse(BaseModel):
    """Tipo de cambio de referencia del colón contra el dólar, del Banco Central."""

    model_config = ConfigDict(from_attributes=True)

    fecha: date
    compra: Decimal
    venta: Decimal


class ResumenFinancieroResponse(BaseModel):
    """Los comprobantes de BAC leídos de la bandeja, y su suma por mes."""

    model_config = ConfigDict(from_attributes=True)

    comprobantes: list[ComprobanteParseadoResponse]
    por_mes: list[ResumenMensualResponse]


class ComprobanteConFuenteResponse(ComprobanteParseadoResponse):
    """Un comprobante, con la cuenta de correo de la que salió.

    Solo lo devuelven los endpoints que combinan varias cuentas: con un solo
    buzón vinculado, saber "de dónde vino" no aporta nada que el titular no
    sepa ya.
    """

    cuenta_correo_id: int
    proveedor: ProveedorCorreo
    direccion_cuenta: str
    # Solo vienen cuando se pidió el resumen en una moneda única y este
    # movimiento hubo que convertirlo. `monto` ya trae el valor convertido;
    # estos dos dicen qué cobró el banco de verdad.
    monto_original: Decimal | None = None
    moneda_original: str | None = None
    # La Compra real que se concilió a partir de este movimiento, si la hubo
    # -con esto el frontend puede pedir GET /api/compras/{id}/bitacora. `None`
    # si la confianza del parseo no alcanzó para conciliar (ver ConciliacionService).
    compra_id: int | None = None
    # De qué día es la tasa con la que se convirtió este movimiento. Puede no
    # ser la de hoy -si se guardó al sincronizarlo- ni la de la compra -si se
    # sincronizó tarde. Va explícito para que la pantalla no tenga que suponer.
    tipo_cambio_fecha: date | None = None


class ResumenFinancieroConFuenteResponse(BaseModel):
    """Como ResumenFinancieroResponse, pero con la cuenta de origen de cada comprobante."""

    model_config = ConfigDict(from_attributes=True)

    comprobantes: list[ComprobanteConFuenteResponse]
    por_mes: list[ResumenMensualResponse]
    # Con qué tasa se convirtió todo, si se pidió una moneda única. Va en la
    # respuesta para que la pantalla pueda decirlo: un total convertido sin
    # decir con qué tasa y de qué día no es un dato, es una cifra suelta.
    conversion: TipoDeCambioResponse | None = None


class ResultadoDeSincronizacionResponse(BaseModel):
    """Cuánto correo nuevo trajo una sincronización explícita."""

    model_config = ConfigDict(from_attributes=True)

    comprobantes_nuevos: int
    comprobantes_totales: int
    sincronizado_en: datetime


class ComercioResponse(BaseModel):
    """Un comercio del catálogo compartido."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    nombre_normalizado: str
    identificacion_tributaria: str | None
    provincia: str | None


class BancoDetectadoResponse(BaseModel):
    """Un remitente que parece un banco, encontrado buscando "banco" en un buzón vinculado.

    Es un candidato, no una confirmación -ver la nota en `BancoDetectado`
    (business/services/cuenta_correo_service.py).
    """

    model_config = ConfigDict(from_attributes=True)

    dominio: str
    remitente_ejemplo: str
    cantidad_mensajes: int
    mensaje_mas_reciente: datetime | None
    es_bac: bool
    cuenta_correo_id: int
    proveedor: ProveedorCorreo
    direccion: str


class TransferenciaSinpeResponse(BaseModel):
    """Una transferencia SINPE recibida, ya leída y parseada, con la cuenta de la que salió.

    BAC y Banco Nacional tienen lector exacto, validado contra una
    notificación real de cada uno (`confirmado=True`). Cualquier otro banco
    pasa por un lector genérico -patrones sueltos, no una plantilla propia-
    y queda con `confirmado=False`: la pantalla lo muestra igual, pero
    marcado para revisar en vez de darlo por bueno. Ver
    `business/parsers/transferencia_sinpe.py`.
    """

    model_config = ConfigDict(from_attributes=True)

    banco: str
    destinatario: str | None
    cuenta_destino: str | None
    fecha: datetime | None
    moneda: str | None
    monto: Decimal | None
    concepto: str | None
    referencia: str | None
    comprobante: str | None
    confianza: float
    es_confiable: bool
    confirmado: bool
    cuenta_correo_id: int
    proveedor: ProveedorCorreo
    direccion_cuenta: str


class ComercioClasificadoResponse(BaseModel):
    """Un comercio real, resuelto del catálogo, con su categoría sugerida (si la hay)."""

    model_config = ConfigDict(from_attributes=True)

    comercio_id: int
    nombre: str
    categoria_id: int | None
    categoria_nombre: str | None
    cantidad_transacciones: int
    total: Decimal
    moneda: str


class AsignarCategoriaComercioRequest(BaseModel):
    """Cuerpo de POST /api/comercios/{id}/categoria."""

    usuario_id: int = Field(gt=0, le=_ID_MAXIMO)
    categoria_id: int = Field(gt=0, le=_ID_MAXIMO)


class CrearPresupuestoRequest(BaseModel):
    """Cuerpo de POST /api/presupuestos.

    Crear el mismo (usuario, categoría, año, mes) dos veces no duplica: la
    segunda llamada corrige el límite de la que ya existía.
    """

    usuario_id: int = Field(gt=0, le=_ID_MAXIMO)
    categoria_id: int = Field(gt=0, le=_ID_MAXIMO)
    anio: int = Field(ge=2000, le=2100)
    mes: int = Field(ge=1, le=12)
    moneda: Moneda
    # < 10**12: lo que de verdad soporta la columna Numeric(14,2). Sin este
    # tope, un valor con más dígitos pasa la validación y revienta en el
    # INSERT con un psycopg.errors.NumericValueOutOfRange sin capturar -un
    # 500 crudo en vez de un 422 con mensaje.
    monto_limite: Decimal = Field(gt=0, lt=Decimal(10**12))
    umbral_alerta: int = Field(default=80, ge=1, le=100)


class PresupuestoResponse(BaseModel):
    """Un presupuesto tal como quedó guardado -sin el consumo, que se calcula aparte."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    categoria_id: int
    anio: int
    mes: int
    moneda: Moneda
    monto_limite: Decimal
    umbral_alerta: int


class CrearMetodoPagoRequest(BaseModel):
    """Cuerpo de POST /api/metodos-pago."""

    usuario_id: int = Field(gt=0, le=_ID_MAXIMO)
    alias: str = Field(min_length=1, max_length=60, examples=["Visa BAC"])
    tipo: TipoMetodoPago
    moneda: Moneda = Moneda.CRC
    ultimos_cuatro: str | None = Field(default=None, min_length=4, max_length=4)
    entidad: str | None = Field(default=None, max_length=80)
    dia_corte: int | None = Field(default=None, ge=1, le=31)


class MetodoPagoResponse(BaseModel):
    """Un método de pago tal como quedó guardado."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    alias: str
    tipo: TipoMetodoPago
    moneda: Moneda
    ultimos_cuatro: str | None
    entidad: str | None
    dia_corte: int | None
    activo: bool


class CrearReglaCategorizacionRequest(BaseModel):
    """Cuerpo de POST /api/reglas-categorizacion."""

    usuario_id: int = Field(gt=0, le=_ID_MAXIMO)
    nombre: str = Field(min_length=1, max_length=80, examples=["Supermercados"])
    patron: str = Field(min_length=1, max_length=200, examples=["WALMART"])
    categoria_destino_id: int = Field(gt=0, le=_ID_MAXIMO)
    campo: CampoRegla = CampoRegla.COMERCIO_NORMALIZADO
    # Sin prioridad, el servicio le asigna la próxima libre -al final de la
    # lista, para no desplazar sin querer una regla que ya existía.
    prioridad: int | None = Field(default=None, ge=1)


class ReglaCategorizacionResponse(BaseModel):
    """Una regla de categorización tal como quedó guardada."""

    id: int
    usuario_id: int
    nombre: str
    campo: CampoRegla
    patron: str
    categoria_destino_id: int
    categoria_destino_nombre: str
    prioridad: int
    activa: bool
    veces_aplicada: int


class ResolverRevisionCompraRequest(BaseModel):
    """Cuerpo de POST /api/compras/{id}/resolver.

    Los dos campos son opcionales pero al menos uno tiene que venir -corregir
    "nada" no es una corrección. Ninguno de los dos se inventa el otro: si
    solo se manda `categoria_id`, el método de pago queda tal como estaba.
    """

    metodo_pago_id: int | None = Field(default=None, gt=0, le=_ID_MAXIMO)
    categoria_id: int | None = Field(default=None, gt=0, le=_ID_MAXIMO)


class CompraResponse(BaseModel):
    """Una compra real, con el nombre de su comercio/método/categoría ya resueltos
    -para no obligar al frontend a pedirlos aparte por cada fila de una lista."""

    id: int
    usuario_id: int
    comercio_id: int
    comercio_nombre: str
    metodo_pago_id: int | None
    metodo_pago_alias: str | None
    categoria_id: int | None
    categoria_nombre: str | None
    fecha: date
    descripcion: str | None
    moneda: Moneda
    total: Decimal
    total_moneda_base: Decimal
    tipo_cambio_aplicado: Decimal
    estado: EstadoCompra
    origen: OrigenCompra
    requiere_revision: bool
    creado_en: datetime


class GastoDeCategoriaResponse(BaseModel):
    """Una fila del gasto del mes agrupado por categoría.

    `categoria_id` es nulo en la fila de lo que quedó sin clasificar -no es un
    error: es justamente el número que le dice al titular cuánto de su mes
    todavía no tiene categoría.
    """

    categoria_id: int | None
    categoria_nombre: str
    total: Decimal
    cantidad_de_renglones: int


class EventoBitacoraResponse(BaseModel):
    """Un evento de la trazabilidad de una compra, tal como vive en Mongo.

    No hereda `from_attributes`: el documento de Mongo llega como `dict`
    plano, no como un objeto con atributos.
    """

    secuencia: int
    tipo: str
    ocurrido_en: datetime
    actor: dict
    datos: dict


class EstadoDePresupuestoResponse(BaseModel):
    """El límite de un presupuesto junto con su consumo real del período."""

    model_config = ConfigDict(from_attributes=True)

    presupuesto_id: int
    categoria_id: int
    categoria_nombre: str
    anio: int
    mes: int
    moneda: str
    monto_limite: Decimal
    monto_consumido: Decimal
    umbral_alerta: int
    porcentaje_usado: float
    estado: EstadoPresupuesto
