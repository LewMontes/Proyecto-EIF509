# API REST · Gastonomo

**Laboratorio 5 · EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026 · Grupo G01**

| | |
|---|---|
| **Integrantes** | Jose Alexis Solís Carvajal · 1-1623-0238 |
| | Luis Antonio Montes de Oca Ruiz · 1-1800-0270 |

Este documento describe el contrato público del sistema: la API REST que expone la
[capa de negocio](negocio.md) a otros sistemas. Cubre el diseño de los recursos, el contrato de
errores, las colecciones paginadas, la seguridad con JWT y roles, la documentación OpenAPI y las
pruebas de integración que verifican todo lo anterior.

El contrato vivo está en **Swagger UI** (`/docs`), que se genera del código; lo que hay acá son las
decisiones detrás de ese contrato y por qué se tomaron.

### Equivalencias del enunciado

El enunciado está redactado para Java 21 + Spring Boot. El equipo tiene autorización para un stack
alternativo ([ADR-001](adr/ADR-001-eleccion-del-stack.md)); estas son las equivalencias, para que
cada punto de la rúbrica se pueda ubicar sin ambigüedad:

| Enunciado | En este proyecto | Dónde |
|---|---|---|
| `@RestController` | Un `APIRouter` por recurso | `presentation/routers/` |
| `@Valid` + Bean Validation | Modelos Pydantic con `Field(...)` y validadores | `presentation/schemas.py` |
| `@RestControllerAdvice` | Manejadores globales registrados en un solo módulo | `presentation/errores.py` |
| `ProblemDetail` | Modelo `ProblemDetail`, `application/problem+json` | `presentation/errores.py` |
| `Pageable` · `Page<T>` | `SolicitudDePagina` · `Pagina[T]` | `data/paginacion.py` |
| `Specification<T>` | `Especificacion`, componible con `y` / `o` | `data/repositories/especificaciones.py` |
| `SecurityFilterChain` stateless | Dependencias `obtener_usuario_actual` y `exigir_rol` | `presentation/dependencies.py` |
| `@PreAuthorize("hasRole(...)")` | `Depends(exigir_rol(RolUsuario.ADMIN))` en el endpoint | `presentation/dependencies.py` |
| springdoc-openapi · Swagger UI | OpenAPI que genera FastAPI · Swagger UI en `/docs` | `main.py` |
| Testcontainers | `testcontainers[postgres]` | `tests/integracion/` |

---

## 1 · Diseño REST

### 1.1 · Las convenciones

- **Versión en la ruta.** Todo el contrato de negocio vive bajo `/api/v1`. Va en la ruta y no en un
  encabezado porque se ve en cualquier registro de acceso y deja convivir a `/api/v1` con una
  futura `/api/v2` como dos árboles de rutas mientras los clientes migran. El prefijo sale de una
  sola constante (`presentation/rutas.py`).
- **Los recursos son sustantivos, en plural; la operación la dice el verbo.** Corregir una compra es
  `PATCH /compras/{id}` y anularla es `DELETE /compras/{id}`. En el Laboratorio 4 eran
  `POST /compras/{id}/resolver` y no existía la anulación.
- **Crear responde `201` con `Location`**, y esa URL se puede consultar: cada `POST` de creación
  tiene su `GET /{id}`.
- **Lo que no devuelve nada responde `204`**: desactivar, anular y eliminar.
- **El titular sale del token.** Ningún endpoint acepta `usuario_id` en el cuerpo ni en la URL.
- **Ninguna entidad del ORM se expone.** Cada respuesta es un DTO de `schemas.py`.
- El único endpoint fuera de `/api/v1` es `GET /api/salud`: no es parte del contrato de negocio que
  se versiona, y quien pregunta si la aplicación está viva todavía no es nadie.

### 1.2 · Los recursos

42 operaciones. **Rol**: `—` público · `T` cualquier cuenta autenticada · `A` solo `ADMIN`.

| Método | Ruta | Rol | Éxito | Qué hace |
|---|---|:---:|:---:|---|
| `GET` | `/api/salud` | — | 200 | La aplicación responde |
| `POST` | `/api/v1/auth/login` | — | 200 | Emite el JWT |
| `POST` | `/api/v1/usuarios` | — | 201 | Registra una cuenta (siempre `TITULAR`) |
| `GET` | `/api/v1/usuarios` | A | 200 | Lista las cuentas · *paginada* |
| `GET` | `/api/v1/usuarios/yo` | T | 200 | La cuenta del token |
| `GET` | `/api/v1/usuarios/{id}` | T | 200 | Una cuenta: la propia, o cualquiera si es `ADMIN` |
| `POST` | `/api/v1/categorias` | T | 201 | Crea una categoría |
| `GET` | `/api/v1/categorias` | T | 200 | Las categorías activas del titular |
| `GET` | `/api/v1/categorias/{id}` | T | 200 | Una categoría |
| `PUT` | `/api/v1/categorias/{id}` | T | 200 | Reemplaza nombre, color y descripción |
| `DELETE` | `/api/v1/categorias/{id}` | T | 204 | La desactiva |
| `POST` | `/api/v1/comercios` | A | 201 | Da de alta un comercio en el catálogo compartido |
| `GET` | `/api/v1/comercios` | T | 200 | El catálogo · *paginado*, filtro `nombre` |
| `GET` | `/api/v1/comercios/{id}` | T | 200 | Un comercio |
| `PUT` | `/api/v1/comercios/{id}/categoria-sugerida` | T | 200 | La categoría que el titular le sugiere |
| `POST` | `/api/v1/metodos-pago` | T | 201 | Registra un método de pago |
| `GET` | `/api/v1/metodos-pago` | T | 200 | Los métodos de pago del titular |
| `GET` | `/api/v1/metodos-pago/{id}` | T | 200 | Un método de pago |
| `DELETE` | `/api/v1/metodos-pago/{id}` | T | 204 | Lo desactiva |
| `POST` | `/api/v1/presupuestos` | T | 201 | Crea el presupuesto de una categoría y un mes |
| `GET` | `/api/v1/presupuestos?anio=&mes=` | T | 200 | Los presupuestos de un período |
| `GET` | `/api/v1/presupuestos/{id}` | T | 200 | Un presupuesto, con lo consumido |
| `PUT` | `/api/v1/presupuestos/{id}` | T | 200 | Corrige el límite y el umbral |
| `DELETE` | `/api/v1/presupuestos/{id}` | T | 204 | Lo elimina |
| `POST` | `/api/v1/reglas-categorizacion` | T | 201 | Crea una regla |
| `GET` | `/api/v1/reglas-categorizacion` | T | 200 | Las reglas, por prioridad |
| `GET` | `/api/v1/reglas-categorizacion/{id}` | T | 200 | Una regla |
| `DELETE` | `/api/v1/reglas-categorizacion/{id}` | T | 204 | La desactiva |
| `POST` | `/api/v1/compras` | T | 201 | **Proceso 1** · registra una compra con desglose |
| `GET` | `/api/v1/compras` | T | 200 | Las compras · *paginada, ordenable, con filtros* |
| `GET` | `/api/v1/compras/gasto-por-categoria` | T | 200 | El gasto del mes, agrupado |
| `GET` | `/api/v1/compras/{id}` | T | 200 | Una compra |
| `PATCH` | `/api/v1/compras/{id}` | T | 200 | Corrige método de pago y/o categoría |
| `DELETE` | `/api/v1/compras/{id}` | T | 204 | La anula y devuelve el monto al presupuesto |
| `GET` | `/api/v1/compras/{id}/bitacora` | T | 200 | Su trazabilidad (MongoDB) |
| `POST` | `/api/v1/cuentas-correo` | T | 201 | Registra un buzón |
| `GET` | `/api/v1/cuentas-correo` | T | 200 | Los buzones del titular |
| `GET` | `/api/v1/cuentas-correo/{id}` | T | 200 | Un buzón |
| `POST` | `/api/v1/comprobantes` | T | 201 | **Proceso 2** · recibe un comprobante y lo concilia |
| `GET` | `/api/v1/comprobantes` | T | 200 | Los comprobantes · *paginada*, filtro `estado` |
| `GET` | `/api/v1/comprobantes/{id}` | T | 200 | Un comprobante |
| `POST` | `/api/v1/comprobantes/{id}/reintentos` | T | 200 | Reintenta la conciliación de uno pendiente |

### 1.3 · Decisiones de diseño que vale la pena justificar

**`PUT` o `PATCH`.** `PUT /categorias/{id}` y `PUT /presupuestos/{id}` reciben la representación
completa de lo editable: repetir la petición deja el recurso igual. `PATCH /compras/{id}` es parcial
de verdad -solo se toca lo que viene en el cuerpo-, porque corregir la categoría de una compra no
tiene que obligar a reenviar su método de pago.

**`DELETE` que no borra.** Categorías, métodos de pago y reglas se **desactivan**; una compra se
**anula**. Ninguna desaparece: un gasto histórico tiene que poder seguir mostrando con qué tarjeta
se pagó y en qué categoría cayó. Se usa `DELETE` igual porque es lo que el cliente quiere decir
-«esto ya no»-, y responde `204`. El recurso sigue consultable por su id, con `activa: false` o
`estado: ANULADA`. `DELETE /presupuestos/{id}` sí borra: un presupuesto no es historial de nada.

**El Proceso 2 es `POST /comprobantes`, no `POST /conciliaciones`.** El recurso que se crea es el
comprobante. Responde `201` siempre que el comprobante quede recibido, se haya conciliado o no:
`estado` dice qué pasó después -`PROCESADO` con su `compra_id`, `REVISION_MANUAL`, o `PARSEADO` si
quedó pendiente del tipo de cambio-. Reintentar crea un intento nuevo, y por eso es
`POST /comprobantes/{id}/reintentos`: un sustantivo, no `/reintentar`.

**`PUT /comercios/{id}/categoria-sugerida`.** La sugerencia es un sub-recurso único por
(titular, comercio): asignarla dos veces la deja igual, que es exactamente la semántica de `PUT`.

**`POST /presupuestos` ya no hace *upsert*.** En el Laboratorio 4 creaba o corregía según el caso, y
un `POST` que a veces crea y a veces modifica no puede responder siempre `201`. Ahora crea, y si ya
existe responde `409`; corregir es `PUT`.

**Qué colecciones se paginan.** Las que crecen sin límite: compras, comprobantes, comercios y
cuentas. Categorías, métodos de pago, reglas y presupuestos de un mes son catálogos acotados por
titular -decenas, no miles- y el cliente los necesita enteros.

---

## 2 · Códigos de estado

| Código | Cuándo | Ejemplo |
|:---:|---|---|
| **200** | Lectura o modificación exitosa | `GET /compras/7` · `PATCH /compras/7` |
| **201** | Se creó un recurso; trae `Location` | `POST /compras` |
| **204** | Éxito sin cuerpo | `DELETE /compras/7` |
| **400** | La petición está **mal formada** | Falta un campo, un tipo no calza, un monto negativo |
| **401** | No hay una identidad válida | Sin token, token vencido, credenciales incorrectas |
| **403** | Hay identidad, pero no le corresponde | Un `TITULAR` en un endpoint de `ADMIN` |
| **404** | El recurso no existe **en esta cuenta** | `GET /compras/999999`, o la compra de otro titular |
| **409** | Choca con el estado actual del recurso | Nombre repetido, compra ya anulada |
| **422** | Bien formada, pero rompe una **regla del dominio** | Fecha futura, rango invertido |
| **500** | Un error que nadie previó | Sin traza: solo un mensaje genérico |
| **502** | Falló un proveedor externo | El Banco Central no responde |

**400 contra 422.** FastAPI responde `422` a todo error de validación. Acá se separan dos cosas que
ese código mezclaba, porque el cliente reacciona distinto a cada una:

- **400** · el formulario está mal: un tipo equivocado, un campo obligatorio que falta, un valor
  fuera de su rango. Lo detecta Pydantic **antes** de llegar al servicio, y la respuesta dice qué
  campo falló.
- **422** · el formulario está bien, pero lo que pide no se puede hacer: la fecha es futura, el
  rango está invertido, el color no es hexadecimal. Lo decide el servicio.

**404 para lo ajeno.** Pedir por id un recurso de otro titular responde `404`, no `403`: el servicio
lo busca por id **y por dueño** a la vez, así que uno ajeno es indistinguible de uno que no existe.
Confirmar que algo existe pero no es tuyo le diría a quien pregunta más de lo que debería. El `403`
queda para cuando no hay nada que ocultar: el rol no alcanza, o se pide la cuenta de otro.

---

## 3 · Errores estándar y validación

### 3.1 · Problem Details (RFC 9457)

Todo error de la API sale con `Content-Type: application/problem+json` y esta forma:

```json
{
  "type": "https://github.com/LewMontes/Proyecto-EIF509/blob/master/docs/api.md#regla-de-negocio-violada",
  "title": "La operación choca con el estado actual del recurso",
  "status": 409,
  "detail": "'Alimentación' es una categoría padre; solo las hojas reciben gasto directo, las padre totalizan.",
  "instance": "/api/v1/compras",
  "codigo": "CategoriaNoEsHoja"
}
```

| Miembro | Qué trae |
|---|---|
| `type` | URI de la **clase** de problema. Resuelve a la sección de este documento que la explica |
| `title` | Resumen fijo de esa clase; no cambia de una ocurrencia a otra |
| `status` | El código HTTP, repetido en el cuerpo |
| `detail` | Lo específico de **esta** ocurrencia: el mensaje de la regla |
| `instance` | La ruta que se pidió |
| `codigo` | *Extensión.* El nombre de la regla de negocio que falló |
| `errores` | *Extensión, solo en un 400.* Cada campo que no pasó la validación |

`codigo` es lo que conecta este contrato con la retroalimentación del Laboratorio 4: cada regla del
dominio tiene ahora su excepción con nombre (`CategoriaNoEsHoja`, `CuadreFueraDeTolerancia`,
`CompraYaAnulada`...), y ese nombre viaja al cliente. Un cliente puede decidir qué hacer por
`codigo` sin interpretar un texto pensado para una persona.

### 3.2 · El manejador global

Vive entero en [`presentation/errores.py`](../src/app/presentation/errores.py). Ningún router tiene
un `try/except` ni arma un error a mano.

| Lo que se lanza | Código | `type` |
|---|:---:|---|
| `RequestValidationError` (Pydantic) | 400 | `#solicitud-mal-formada` |
| `NoAutenticado` y sus reglas | 401 | `#no-autenticado` |
| `AccesoDenegado` | 403 | `#acceso-denegado` |
| `RecursoNoEncontrado` | 404 | `#recurso-no-encontrado` |
| `ReglaDeNegocioViolada` y sus 20 reglas con nombre | 409 | `#regla-de-negocio-violada` |
| `DatosInvalidos` y sus 7 reglas con nombre | 422 | `#datos-invalidos` |
| `ErrorDeProveedorExterno` | 502 | `#proveedor-externo` |
| `IntegrityError` de la base | 409 | `#regla-de-negocio-violada` |
| Errores del framework (ruta inexistente, método no permitido) | 404 · 405 | `about:blank` |
| Cualquier otra `Exception` | 500 | `#error-interno` |

Un solo manejador atiende **toda** la jerarquía de `ErrorDeNegocio`: busca de qué familia hereda la
excepción y de ahí saca el código. Agregar una regla con nombre nueva no toca este archivo.

**Ninguna traza llega al cliente.** El manejador de `Exception` responde un `500` con un mensaje
fijo y deja la traza en el log del servidor. Lo mismo el de `IntegrityError`, cuyo mensaje original
nombra tablas y restricciones. `test_500_un_error_inesperado_no_expone_nada_del_interior` lo fija:
provoca un error cuyo mensaje trae una cadena de conexión y verifica que no aparezca en la
respuesta.

### 3.3 · Las clases de problema

<a id="solicitud-mal-formada"></a>
**Solicitud mal formada · 400.** Un campo no pasó la validación de formato. `errores` trae la ruta
de cada campo (`body.lineas.0.cantidad`, `query.orden.0`) y el motivo.

<a id="no-autenticado"></a>
**No autenticado · 401.** Falta el token, venció, su firma no calza, o la cuenta ya no está activa.
También las credenciales incorrectas del login. Trae el encabezado `WWW-Authenticate: Bearer`.

<a id="acceso-denegado"></a>
**Acceso denegado · 403.** La identidad es válida, pero la operación exige otro rol, o el recurso es
de otra cuenta.

<a id="recurso-no-encontrado"></a>
**Recurso no encontrado · 404.** No existe, o no pertenece al titular que lo pide.

<a id="regla-de-negocio-violada"></a>
**Regla de negocio violada · 409.** La petición es válida, pero choca con el estado actual: un
nombre que ya existe, una categoría padre que no recibe gasto, una compra ya anulada, un
comprobante que ya se había recibido.

<a id="datos-invalidos"></a>
**Datos inválidos · 422.** La forma es correcta pero rompe una regla del dominio: una fecha futura,
un descuento mayor que el monto, un rango invertido.

<a id="proveedor-externo"></a>
**Proveedor externo · 502.** Un servicio del que el sistema depende no respondió. No es un error
del cliente.

<a id="error-interno"></a>
**Error interno · 500.** Algo que nadie previó. El detalle queda en el log del servidor.

### 3.4 · La validación de formato

Es el equivalente de `@Valid`: cada DTO de entrada declara sus restricciones y FastAPI las aplica
antes de llamar al endpoint.

```python
class RegistrarComprobanteRequest(BaseModel):
    cuenta_correo_id: int = Field(gt=0, le=_ID_MAXIMO)
    mensaje_id: str = Field(min_length=1, max_length=255)
    monto: Decimal = Field(gt=0, lt=Decimal(10**12))  # monto positivo
    moneda: Moneda  # una moneda que el sistema reconoce
    fecha: datetime
    ultimos_cuatro: str | None = Field(default=None, pattern=r"^[0-9]{4}$")

    @field_validator("fecha")
    @classmethod
    def _no_futura(cls, valor: datetime) -> datetime:  # fecha no futura
        if valor > datetime.now(valor.tzinfo):
            raise ValueError("La fecha del comprobante no puede ser futura.")
        return valor.replace(tzinfo=None)
```

Es el DTO que pidió la retroalimentación del Laboratorio 4 para el Proceso 2. Los ids que viajan en
la ruta también se validan (`IdDeRuta`): uno que no cabe en la columna es un `400`, no un error de
la base.

Los DTOs validan **solo la forma**. Si la operación se puede hacer o no es una pregunta del negocio
y se responde en el servicio: por eso un color de siete caracteres que no es hexadecimal pasa la
validación (`400` no) y lo rechaza la regla (`422` sí).

---

## 4 · Paginación, orden y filtros

### 4.1 · El contrato de una colección

```
GET /api/v1/compras?pagina=0&tamano=20&orden=fecha,desc&orden=total,asc
```

```json
{
  "contenido": [ { "id": 41, "fecha": "2026-08-30", "...": "..." } ],
  "pagina": 0,
  "tamano": 20,
  "total_elementos": 137,
  "total_paginas": 7,
  "primera": true,
  "ultima": false,
  "orden": ["fecha,desc", "total,asc"]
}
```

| Parámetro | Por defecto | Regla |
|---|---|---|
| `pagina` | `0` | Desde cero. Negativa → `400` |
| `tamano` | `20` | Entre 1 y 100 → si no, `400` |
| `orden` | el del recurso | `campo,asc` o `campo,desc`. Repetible para ordenar por varios |

Una página más allá del final no es un error: viene con `contenido` vacío y el mismo
`total_elementos`.

### 4.2 · Cómo se pagina

`data/paginacion.py` tiene las tres piezas: `SolicitudDePagina` (lo que se pide), `Pagina[T]` (el
contenido con sus metadatos) y `paginar`, que convierte un `SELECT` cualquiera en una página:

- **Dos consultas**: un `COUNT(*)` sobre los mismos filtros y el `SELECT` con `ORDER BY`, `LIMIT` y
  `OFFSET`. El total sale de la base, no de `len()` de todo el resultado.
- **Lista cerrada de campos ordenables.** El nombre que manda el cliente nunca llega a la consulta:
  se usa como llave de un diccionario que declara cada repositorio. Pedir
  `orden=contrasena_hash,desc` es un `400`, no una columna que alguien logró inyectar.
- **Desempate siempre al final.** Sin un orden total, dos filas que empatan en el criterio pedido
  pueden cambiar de lugar entre una consulta y la siguiente, y la misma fila aparecería en dos
  páginas o en ninguna. `test_recorrer_las_paginas_no_repite_ni_pierde_ninguna_compra` lo fija.

| Colección | Campos ordenables | Por defecto |
|---|---|---|
| `/compras` | `fecha` · `total` · `creado_en` · `id` | `fecha,desc` |
| `/comprobantes` | `recibido_en` · `fecha` · `monto` · `id` | `recibido_en,desc` |
| `/comercios` | `nombre` · `id` | `nombre,asc` |
| `/usuarios` | `correo` · `nombre` · `creado_en` · `id` | `correo,asc` |

`total` ordena por el total **en moneda base**: ordenar por el crudo mezclaría dólares y colones.

### 4.3 · Los filtros de negocio, con Specifications

`GET /api/v1/compras` admite diez filtros, todos opcionales y combinables:

| Parámetro | Especificación | Filtra |
|---|---|---|
| *(el token)* | `del_titular` | **Siempre.** No es opcional ni viene del cliente |
| `desde` · `hasta` | `entre_fechas` | Fecha de la compra, extremos inclusive |
| `categoria_id` | `de_la_categoria` | Compras con algún renglón en esa categoría |
| `comercio_id` | `del_comercio` | |
| `metodo_pago_id` | `con_metodo_de_pago` | |
| `estado` | `en_estado` | `REGISTRADA`, `ANULADA`... |
| `origen` | `de_origen` | `MANUAL` o `INGESTA_CORREO` |
| `requiere_revision` | `que_requieren_revision` | Las que quedaron sin tarjeta o sin categoría |
| `total_minimo` · `total_maximo` | `con_total_entre` | Sobre el total en moneda base |

Cada filtro es una **especificación**: un objeto con nombre de negocio que sabe convertirse en un
predicado SQL, y que se compone con otros.

```python
@dataclass(frozen=True)
class Especificacion:
    criterio: ColumnElement[bool] | None = None  # sin criterio, no filtra

    def y(self, otra: "Especificacion") -> "Especificacion": ...
    def o(self, otra: "Especificacion") -> "Especificacion": ...
    def como_predicado(self) -> ColumnElement[bool]: ...


def de_la_categoria(categoria_id: int | None) -> Especificacion:
    if categoria_id is None:
        return Especificacion()  # el filtro no vino: no filtra
    return Especificacion(
        Compra.id.in_(select(LineaCompra.compra_id).where(LineaCompra.categoria_id == categoria_id))
    )
```

El servicio las compone y el repositorio recibe **una sola**, sin saber de cuántas piezas está
hecha:

```python
especificacion = esp.todas(
    esp.del_titular(usuario_id),
    esp.entre_fechas(filtros.desde, filtros.hasta),
    esp.de_la_categoria(filtros.categoria_id),
    ...,
)
return self.compras.buscar(especificacion, solicitud).convertir(self._detallar)
```

Lo que esto resuelve: con un parámetro por filtro, cada filtro nuevo agregaba un parámetro y un
`if` al repositorio. Ahora un filtro nuevo es una función en `especificaciones.py` y una línea en el
servicio; `CompraRepository.buscar` no se toca.

`de_la_categoria` es una subconsulta y no un `JOIN` a propósito: la categoría vive en el renglón, y
con un `JOIN` una compra con dos renglones de la misma categoría saldría dos veces y descuadraría
el conteo de la página.

---

## 5 · Seguridad

### 5.1 · El flujo

```
  Cliente                                  API                            Base
     │  POST /api/v1/auth/login              │                               │
     │  { correo, contrasena } ─────────────▶│  buscar por correo ──────────▶│
     │                                       │◀──────── usuario + hash ──────│
     │                                       │  bcrypt.checkpw               │
     │                                       │  firmar JWT (HS256)           │
     │◀──── 200 { access_token, expires_in } │                               │
     │                                       │                               │
     │  GET /api/v1/compras                  │                               │
     │  Authorization: Bearer <token> ──────▶│  verificar firma y `exp`      │
     │                                       │  releer la cuenta (sub) ─────▶│
     │                                       │◀──────── activo, rol ─────────│
     │                                       │  ¿el rol alcanza?             │
     │                                       │  servicio(usuario_id = sub) ─▶│  WHERE usuario_id = …
     │◀──────────────── 200 { contenido … }  │                               │
```

1. **Login.** `POST /auth/login` verifica la contraseña contra su hash de bcrypt y firma un JWT.
   El error es el mismo -mismo código, mismo mensaje- para un correo que no existe y para una
   contraseña equivocada: distinguirlos le confirmaría a quien prueba correos cuáles tienen cuenta.
2. **Cada petición** trae `Authorization: Bearer <token>`. `obtener_usuario_actual` verifica la
   firma y el vencimiento, y relee la cuenta.
3. **Autorización por rol**, si el endpoint la pide.
4. **Propiedad del recurso**, en el servicio.

### 5.2 · Stateless

No hay sesión de servidor, ni cookie, ni tabla de tokens: **el token es la sesión**. Cada petición
se autentica sola, y dos peticiones del mismo cliente pueden caer en dos instancias distintas de la
aplicación sin compartir nada. Por eso tampoco hay `logout`: no hay nada que borrar del lado del
servidor. El token vence solo (60 minutos por defecto, `GASTONOMO_JWT_MINUTOS`).

### 5.3 · El token

Firmado con HS256 y `GASTONOMO_JWT_SECRETO`. Lleva cuatro afirmaciones y nada más:

| *Claim* | Qué es |
|---|---|
| `sub` | El id del titular. De acá sale el `usuario_id` de **toda** operación |
| `rol` | `TITULAR` o `ADMIN` |
| `iat` | Cuándo se emitió |
| `exp` | Cuándo vence |

Un JWT va firmado, no cifrado: cualquiera puede leerlo. Por eso no lleva ningún dato sensible.

**El rol que vale es el de la base, no el del token.** `AuthService.usuario_de_token` relee la
cuenta en cada petición. Es una consulta por llave primaria, a cambio de que desactivar a alguien
-o quitarle el rol de administrador- surta efecto de inmediato en vez de esperar a que su token
venza, y sin necesitar una lista de tokens revocados.

`leer_token` fija `algorithms=["HS256"]`: sin esa lista, un token con `alg: none` -sin firma-
pasaría la verificación.

### 5.4 · Dos roles, autorización por endpoint

| Rol | Quién | Qué puede |
|---|---|---|
| `TITULAR` | Cualquiera que se registra | Todo sobre **sus** datos |
| `ADMIN` | Sembrado al arrancar | Además: dar de alta comercios en el catálogo compartido, listar las cuentas y consultar cualquiera |

El rol que exige cada ruta queda escrito al lado de la ruta:

```python
Administrador = Annotated[UsuarioAutenticado, Depends(exigir_rol(RolUsuario.ADMIN))]


@router.post("", status_code=201)
def crear(peticion: CrearComercioRequest, servicio: ServicioDeComercios, _: Administrador): ...
```

`exigir_rol` depende de `obtener_usuario_actual`: primero autentica (`401` si no hay identidad) y
recién después autoriza (`403` si la identidad no alcanza).

**Un administrador no gana acceso a los gastos de nadie.** El aislamiento por titular no depende
del rol: sus endpoints son sobre lo que es de todos.

**Registrarse siempre crea un `TITULAR`.** El DTO de registro no tiene campo `rol`; si lo tuviera,
cualquiera se registraría como administrador. El primer `ADMIN` nace del arranque, de
`GASTONOMO_ADMIN_CORREO` y `GASTONOMO_ADMIN_CONTRASENA`. Sin esas variables no se crea ninguno: no
hay un administrador con una contraseña por defecto que alguien pueda adivinar.

### 5.5 · Propiedad del recurso, en el servicio (OWASP API1)

*Broken Object Level Authorization* es el riesgo número uno de OWASP para APIs: que alguien
autenticado pida por id un objeto que no es suyo y la API se lo dé. Se cierra en tres lugares, y
ninguno es el router:

**1 · El `usuario_id` nunca viene del cliente.** Sale del `sub` del token. No hay un parámetro que
manipular: mandar `usuario_id` en el cuerpo no cambia nada
(`test_mandar_usuario_id_en_el_cuerpo_no_cambia_el_dueno`).

**2 · Todo recurso se busca por id y por dueño a la vez.** Los servicios no tienen un «buscar por
id»: tienen `obtener_de_usuario(id, usuario_id)`.

```python
def anular(self, usuario_id: int, compra_id: int) -> CompraAnulada:
    compra = self.compras.obtener_de_usuario(compra_id, usuario_id)
    if compra is None:
        raise RecursoNoEncontrado(f"La compra {compra_id} no existe en esta cuenta.")
```

Vale también para lo que una operación **referencia**: registrar una compra con la categoría de
otro titular responde `404`, igual que conciliar un comprobante contra un buzón ajeno.

**3 · Las colecciones arrancan siempre de `del_titular`.** Ningún filtro que mande el cliente puede
sacar la búsqueda de sus propias compras.

Donde la verificación es más literal es en las cuentas, porque ahí sí hay dos resultados posibles:

```python
def obtener(self, solicitante: UsuarioAutenticado, usuario_id: int) -> UsuarioDetalle:
    if solicitante.id != usuario_id and not solicitante.es_admin:
        raise AccesoDenegado("Solo podés consultar tu propia cuenta.")
```

Se verifica **antes** de buscar la cuenta: al revés, un titular podría distinguir un `404` de un
`403` y enumerar qué ids existen.

---

## 6 · Documentación OpenAPI y colección de peticiones

**Swagger UI** está en [`/docs`](http://127.0.0.1:8000/docs) y el contrato crudo en
`/openapi.json`. Se generan del código -los routers, los DTOs y sus `Field(...)`-, así que no pueden
quedar desactualizados respecto de lo que la API hace.

Lo que se le agregó al contrato generado:

- **El esquema de seguridad `bearer`**: Swagger UI muestra el botón **Authorize**, y cada endpoint
  protegido su candado. Los tres públicos (`/salud`, `/auth/login`, `POST /usuarios`) no lo llevan.
- **Los errores, con su forma real.** Cada operación declara sus respuestas `400`, `401`, `403`,
  `404`, `409` y `422` como `ProblemDetail` y con `application/problem+json`. FastAPI documenta por
  defecto un `422` con `HTTPValidationError`, que ya no es lo que esta API devuelve: se reemplazó.
- **Una descripción** con el paso a paso para autenticarse desde la propia página, y una
  descripción por grupo de endpoints.

Para probarla desde Swagger UI: `POST /usuarios` → `POST /auth/login` → copiar el `access_token` en
**Authorize**.

**La colección de peticiones** es [`docs/api/gastonomo.http`](api/gastonomo.http): un archivo `.http`
que ejercita **las 42 operaciones** y, al final, un caso por cada código de error. Se corre de
arriba hacia abajo -cada petición usa lo que crearon las anteriores- con la extensión *REST Client*
de VS Code.

---

## 7 · Pruebas de integración

[`tests/integracion/test_api_postgres.py`](../tests/integracion/test_api_postgres.py) hace peticiones
HTTP a la aplicación verdadera, que corre sobre un `postgres:16-alpine` levantado con
**Testcontainers** y con el esquema de las migraciones de Flyway (`V1`…`V8`). No hay SQLite ni
dobles de repositorio: responde el recorrido completo, con las restricciones reales de la base.

```bash
pytest -m integracion
```

| Código | Pruebas que lo verifican |
|:---:|---|
| **201** | `test_201_registrarse_e_iniciar_sesion_contra_la_base_real` · `test_201_crear_devuelve_location_y_el_recurso_se_puede_consultar` (×3) · `test_201_un_administrador_da_de_alta_un_comercio` |
| **204** | `test_204_desactivar_no_devuelve_cuerpo` |
| **400** | `test_400_un_dto_mal_formado_no_llega_a_la_base` (×3) · `test_400_un_comprobante_con_monto_negativo_o_fecha_futura` · `test_400_un_orden_por_un_campo_que_no_existe` |
| **401** | `test_401_sin_token_ningun_endpoint_de_negocio_responde` (×7) · `test_401_con_la_contrasena_equivocada` · `test_401_con_un_token_que_no_firmo_este_servidor` |
| **403** | `test_403_un_titular_no_entra_a_los_endpoints_de_administrador` · `test_403_un_titular_no_consulta_la_cuenta_de_otro` |
| **404** | `test_404_un_recurso_que_no_existe` (×8) · `test_404_lo_de_otro_titular_es_indistinguible_de_lo_que_no_existe` |
| **409** | `test_409_un_nombre_repetido` · `test_409_una_categoria_padre_no_recibe_gasto` |
| **422** | `test_422_un_dato_bien_formado_que_rompe_una_regla_del_dominio` · `test_422_una_compra_en_dolares_sin_su_tipo_de_cambio` · `test_422_un_rango_de_fechas_invertido` |

Más los dos procesos completos (`test_proceso_1_registrar_corregir_y_anular_una_compra`,
`test_proceso_2_un_comprobante_escribe_las_cinco_tablas`) y la colección paginada con el `COUNT` y
el `ORDER BY` de PostgreSQL.

Lo que estas pruebas detectan y las de SQLite no: que el mapeo calce con el esquema de Flyway. El
Proceso 2 pasa por las llaves foráneas compuestas de `V3` -el renglón y el comprobante tienen que
ser del mismo titular que la compra- y por el `CHECK` que exige que un comprobante `PROCESADO`
tenga su compra.

Aparte, sobre SQLite en memoria y sin Docker, el contrato tiene sus pruebas rápidas:

| Archivo | Qué cubre |
|---|---|
| `tests/test_seguridad_api.py` | Login, token alterado · vencido · firmado con otra clave, roles, propiedad |
| `tests/test_errores_api.py` | Problem Details por cada código, que el `500` no filtra nada, el contrato OpenAPI |
| `tests/test_paginacion_api.py` | Especificaciones, metadatos, orden, cada filtro y sus combinaciones |
| `tests/test_catalogos_api.py` | `201` + `Location`, `204`, `404` y `409` de cada entidad |
| `tests/test_compras_api.py` · `tests/test_comprobantes_api.py` | Los dos procesos por la API |

---

## 8 · Lo que queda abierto

1. **No hay *refresh token*.** Cuando el token vence hay que iniciar sesión de nuevo. Con un token
   de 60 minutos y sin revocación, es el punto medio que se eligió; uno de refresco exige guardar
   estado en el servidor, que es justo lo que el diseño *stateless* evita.
2. **Un token no se puede revocar antes de que venza**, salvo desactivando la cuenta -que sí surte
   efecto de inmediato, porque la cuenta se relee en cada petición.
3. **No hay límite de intentos de login.** Un atacante puede probar contraseñas contra
   `/auth/login` sin que nada lo frene más que el costo de bcrypt.
4. **El buzón se registra, no se enlaza.** `POST /cuentas-correo` crea el buzón al que pertenecen
   los comprobantes; el intercambio OAuth2 con Microsoft o Google queda fuera de esta entrega, así
   que el comprobante entra por `POST /comprobantes` ya leído, no lo lee el sistema del correo.
5. **Los servicios de catálogo devuelven la entidad del ORM** al router, que la convierte a su DTO
   antes de responder ([Capa de negocio § 4.3](negocio.md#43--dónde-la-frontera-todavía-no-es-estricta)).
   Ninguna entidad se expone en la API, pero sí cruza de negocio a presentación.

---

## Documentos relacionados

| Documento | Qué contiene |
|---|---|
| [Capa de negocio](negocio.md) | Los dos procesos, sus reglas, los patrones y la respuesta a la retroalimentación del Laboratorio 4 |
| [Capa de persistencia](persistencia.md) | Mapeo ORM, repositorios y consultas |
| [Propuesta de dominio](propuesta-dominio.md) | El negocio, las entidades y los procesos |
| [ADR-001](adr/ADR-001-eleccion-del-stack.md) | Por qué Python + FastAPI en lugar de Java + Spring Boot |
