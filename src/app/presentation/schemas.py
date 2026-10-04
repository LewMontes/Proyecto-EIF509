"""DTOs de entrada y salida de la API.

Viven en presentacion, no en negocio: describen el contrato HTTP y pueden
cambiar sin que el dominio se entere.

Dos reglas que valen para todos:

- **Ningún DTO de entrada trae `usuario_id`.** El titular de una operación
  sale del token (`sub`), nunca del cuerpo ni de la URL: si el cliente pudiera
  decir a nombre de quién actúa, la autorización no serviría de nada.
- **Solo validan la forma del dato** -tipos, largos, rangos, formato-. Si la
  operación se puede hacer o no es una pregunta del negocio, y se responde en
  el servicio.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.data.models.enums import (
    CampoRegla,
    EstadoCompra,
    EstadoComprobante,
    EstadoCuentaCorreo,
    Moneda,
    OrigenCompra,
    ProveedorCorreo,
    RolUsuario,
    TipoMetodoPago,
)

# El tope de un INTEGER de PostgreSQL. Un id más grande es un entero válido
# para Python, pero la base lo rechaza al convertirlo: se corta acá, como error
# de forma, en vez de dejar que llegue a la consulta.
_ID_MAXIMO = 2_147_483_647

# Un id que viaja en la ruta (`/compras/{compra_id}`).
IdDeRuta = Annotated[int, Path(gt=0, le=_ID_MAXIMO)]


class SaludResponse(BaseModel):
    """Respuesta del endpoint de salud."""

    estado: str
    aplicacion: str
    version: str


# ---- autenticación y cuentas ----


class LoginRequest(BaseModel):
    """Cuerpo de POST /api/v1/auth/login."""

    correo: str = Field(min_length=3, max_length=180, examples=["ana@gastonomo.cr"])
    contrasena: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    """El token de acceso. Va en `Authorization: Bearer <access_token>` de cada petición."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos que le quedan de vida al token.")
    rol: RolUsuario


class RegistrarUsuarioRequest(BaseModel):
    """Cuerpo de POST /api/v1/usuarios.

    No trae `rol`: toda cuenta que se registra nace `TITULAR`.
    """

    nombre_completo: str = Field(min_length=1, max_length=120, examples=["Ana Mora"])
    correo: str = Field(min_length=3, max_length=180, examples=["ana@gastonomo.cr"])
    # 72 es el tope real de bcrypt: lo que pase de ahí no entraría en el hash.
    contrasena: str = Field(min_length=8, max_length=72)


class UsuarioResponse(BaseModel):
    """Una cuenta, sin el hash de su contraseña."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_completo: str
    correo: str
    moneda_preferida: Moneda
    rol: RolUsuario
    activo: bool
    creado_en: datetime


# ---- categorías ----


class CrearCategoriaRequest(BaseModel):
    """Cuerpo de POST /api/v1/categorias."""

    nombre: str = Field(min_length=1, max_length=60, examples=["Alimentacion"])
    color_hex: str = Field(default="#6B7280", min_length=7, max_length=7, examples=["#2563EB"])
    descripcion: str | None = Field(default=None, max_length=255)
    categoria_padre_id: int | None = Field(
        default=None,
        gt=0,
        le=_ID_MAXIMO,
        description="Categoria que la totaliza, si es subcategoria",
    )


class ActualizarCategoriaRequest(BaseModel):
    """Cuerpo de PUT /api/v1/categorias/{id}: reemplaza nombre, color y descripción."""

    nombre: str = Field(min_length=1, max_length=60)
    color_hex: str = Field(min_length=7, max_length=7, examples=["#2563EB"])
    descripcion: str | None = Field(default=None, max_length=255)


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


# ---- comercios ----


class CrearComercioRequest(BaseModel):
    """Cuerpo de POST /api/v1/comercios. Solo para administradores."""

    nombre: str = Field(min_length=1, max_length=120, examples=["Walmart San Sebastián"])
    identificacion_tributaria: str | None = Field(default=None, pattern=r"^[0-9]{9,12}$")
    provincia: str | None = Field(default=None, max_length=40)


class ComercioResponse(BaseModel):
    """Un comercio del catálogo compartido."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    nombre_normalizado: str
    identificacion_tributaria: str | None
    provincia: str | None


class AsignarCategoriaComercioRequest(BaseModel):
    """Cuerpo de PUT /api/v1/comercios/{id}/categoria-sugerida."""

    categoria_id: int = Field(gt=0, le=_ID_MAXIMO)


# ---- métodos de pago ----


class CrearMetodoPagoRequest(BaseModel):
    """Cuerpo de POST /api/v1/metodos-pago."""

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


# ---- presupuestos ----


class CrearPresupuestoRequest(BaseModel):
    """Cuerpo de POST /api/v1/presupuestos."""

    categoria_id: int = Field(gt=0, le=_ID_MAXIMO)
    anio: int = Field(ge=2000, le=2100)
    mes: int = Field(ge=1, le=12)
    moneda: Moneda
    monto_limite: Decimal = Field(gt=0, lt=Decimal(10**12))
    umbral_alerta: int = Field(default=80, ge=1, le=100)


class ActualizarPresupuestoRequest(BaseModel):
    """Cuerpo de PUT /api/v1/presupuestos/{id}: corrige el límite y el umbral."""

    monto_limite: Decimal = Field(gt=0, lt=Decimal(10**12))
    umbral_alerta: int = Field(ge=1, le=100)


class PresupuestoResponse(BaseModel):
    """Un presupuesto, con lo que lleva consumido."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: int
    categoria_id: int
    anio: int
    mes: int
    moneda: Moneda
    monto_limite: Decimal
    monto_consumido: Decimal
    umbral_alerta: int


# ---- reglas de categorización ----


class CrearReglaCategorizacionRequest(BaseModel):
    """Cuerpo de POST /api/v1/reglas-categorizacion."""

    nombre: str = Field(min_length=1, max_length=80, examples=["Supermercados"])
    patron: str = Field(min_length=1, max_length=200, examples=["WALMART"])
    categoria_destino_id: int = Field(gt=0, le=_ID_MAXIMO)
    campo: CampoRegla = CampoRegla.COMERCIO_NORMALIZADO
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


# ---- compras (Proceso 1) ----


class LineaDeCompraRequest(BaseModel):
    """Un renglón del desglose, en el cuerpo de POST /api/v1/compras.

    Solo valida la forma: que la cantidad sea positiva y el precio no
    negativo. Que el descuento no supere el monto del renglón, o que la
    categoría sea hoja y del titular, son preguntas del negocio y las
    responde `RegistrarCompraService`.
    """

    descripcion: str = Field(min_length=1, max_length=255, examples=["Leche 1L"])
    cantidad: Decimal = Field(gt=0, lt=Decimal(10**9), examples=["2"])
    precio_unitario: Decimal = Field(ge=0, lt=Decimal(10**12), examples=["1250.00"])
    descuento: Decimal = Field(default=Decimal("0"), ge=0, lt=Decimal(10**12))
    exento_impuesto: bool = False
    categoria_id: int | None = Field(default=None, gt=0, le=_ID_MAXIMO)


class RegistrarCompraRequest(BaseModel):
    """Cuerpo de POST /api/v1/compras -el Proceso 1 del dominio.

    Es la captura manual, para una compra que no llegó por correo. A
    diferencia de la ingesta, acá sí hay desglose: varios renglones, cada uno
    con su propia categoría y su propio tratamiento de impuesto.
    """

    comercio_id: int = Field(gt=0, le=_ID_MAXIMO)
    fecha: date
    lineas: list[LineaDeCompraRequest] = Field(min_length=1, max_length=100)
    moneda: Moneda = Moneda.CRC
    metodo_pago_id: int | None = Field(default=None, gt=0, le=_ID_MAXIMO)
    descripcion: str | None = Field(default=None, max_length=255)
    descuento: Decimal = Field(default=Decimal("0"), ge=0, lt=Decimal(10**12))
    total_declarado: Decimal | None = Field(default=None, ge=0, lt=Decimal(10**12))
    tipo_cambio_aplicado: Decimal | None = Field(default=None, gt=0, lt=Decimal(10**6))


class LineaCompraResponse(BaseModel):
    """Un renglón ya calculado y clasificado."""

    linea_id: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    descuento: Decimal
    exento_impuesto: bool
    subtotal: Decimal
    impuesto: Decimal
    categoria_id: int
    categoria_nombre: str
    categorizada_automaticamente: bool


class CompraRegistradaResponse(BaseModel):
    """La compra recién registrada, con su desglose y sus totales calculados.

    `presupuestos_alertados` trae los presupuestos que cruzaron su umbral con
    esta compra -para que la pantalla pueda avisarlo en el momento, sin tener
    que volver a consultar el estado de cada uno.
    """

    compra_id: int
    fecha: date
    comercio_nombre: str
    metodo_pago_alias: str | None
    moneda: Moneda
    estado: EstadoCompra
    subtotal: Decimal
    descuento: Decimal
    impuesto: Decimal
    total: Decimal
    tipo_cambio_aplicado: Decimal
    total_moneda_base: Decimal
    lineas: list[LineaCompraResponse]
    presupuestos_alertados: list[int]


class CorregirCompraRequest(BaseModel):
    """Cuerpo de PATCH /api/v1/compras/{id}.

    Los dos campos son opcionales pero al menos uno tiene que venir -corregir
    «nada» no es una corrección. Ninguno de los dos se inventa el otro: si
    solo se manda `categoria_id`, el método de pago queda tal como estaba.
    """

    metodo_pago_id: int | None = Field(default=None, gt=0, le=_ID_MAXIMO)
    categoria_id: int | None = Field(default=None, gt=0, le=_ID_MAXIMO)

    @model_validator(mode="after")
    def _al_menos_un_campo(self) -> "CorregirCompraRequest":
        if self.metodo_pago_id is None and self.categoria_id is None:
            raise ValueError("Hay que mandar metodo_pago_id, categoria_id o los dos.")
        return self


class CompraResponse(BaseModel):
    """Una compra real, con el nombre de su comercio/método/categoría ya resueltos
    -para no obligar al cliente a pedirlos aparte por cada fila de una lista."""

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
    """Un evento de la trazabilidad de una compra, tal como vive en Mongo."""

    secuencia: int
    tipo: str
    ocurrido_en: datetime
    actor: dict
    datos: dict


# ---- buzones y comprobantes (Proceso 2) ----


class RegistrarCuentaCorreoRequest(BaseModel):
    """Cuerpo de POST /api/v1/cuentas-correo."""

    proveedor: ProveedorCorreo
    direccion: str = Field(min_length=3, max_length=180, examples=["ana@gmail.com"])


class CuentaCorreoResponse(BaseModel):
    """Un buzón del titular, sin ningun dato de token."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    proveedor: ProveedorCorreo
    direccion: str
    estado: EstadoCuentaCorreo
    ultima_sincronizacion: datetime | None


class RegistrarComprobanteRequest(BaseModel):
    """Cuerpo de POST /api/v1/comprobantes -la entrada del Proceso 2.

    Trae los campos que el lector extrajo de la notificación del banco, nunca
    el cuerpo del correo. La forma se valida acá, antes de llegar al negocio:
    **monto positivo, fecha que no sea futura y una moneda que el sistema
    reconozca**. `comercio` y `ultimos_cuatro` sí pueden faltar: un comprobante
    incompleto no es un error de formato, es un caso del negocio -queda en
    revisión manual-.
    """

    cuenta_correo_id: int = Field(gt=0, le=_ID_MAXIMO)
    mensaje_id: str = Field(min_length=1, max_length=255, examples=["AAMkAGI2-0001"])
    remitente: str = Field(min_length=3, max_length=180, examples=["notificacion@baccredomatic.cr"])
    banco: str = Field(min_length=1, max_length=80, examples=["BAC Credomatic"])
    comercio: str | None = Field(default=None, min_length=1, max_length=200)
    monto: Decimal = Field(gt=0, lt=Decimal(10**12), examples=["7870.00"])
    moneda: Moneda
    fecha: datetime = Field(description="Fecha y hora de la compra según la notificación.")
    ultimos_cuatro: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    tipo_transaccion: str = Field(default="COMPRA", min_length=1, max_length=40)
    confianza: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="La que calculó el lector. Sin ella se deriva de los campos presentes.",
    )

    @field_validator("fecha")
    @classmethod
    def _no_futura(cls, valor: datetime) -> datetime:
        """Una compra que todavía no ocurrió no es un comprobante.

        Se compara en la zona del propio valor, y se devuelve sin zona: la
        columna guarda la hora local que el banco escribió en la notificación.
        """
        if valor > datetime.now(valor.tzinfo):
            raise ValueError("La fecha del comprobante no puede ser futura.")
        return valor.replace(tzinfo=None)


class ComprobanteResponse(BaseModel):
    """Un comprobante y dónde quedó dentro de la ingesta."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cuenta_correo_id: int
    mensaje_id: str
    remitente: str
    recibido_en: datetime
    estado: EstadoComprobante
    banco: str
    comercio: str | None
    monto: Decimal | None
    moneda: str | None
    fecha: datetime | None
    ultimos_cuatro: str | None
    tipo_transaccion: str | None
    confianza: float
    intentos_procesamiento: int
    motivo_fallo: str | None
    compra_id: int | None
