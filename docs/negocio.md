# Capa de negocio · Gastonomo

**Laboratorio 4 · EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026 · Grupo G01**

| | |
|---|---|
| **Integrantes** | Jose Alexis Solís Carvajal · 1-1623-0238 |
| | Luis Antonio Montes de Oca Ruiz · 1-1800-0270 |

Este documento describe la capa de negocio: los procesos de la
[propuesta de dominio](propuesta-dominio.md) implementados como servicios con reglas, cálculos y
validaciones; la garantía transaccional del proceso multi-paso; la frontera de DTOs que protege al
dominio; y los patrones de diseño aplicados, cada uno con la señal concreta que lo justificó.

Se apoya en la [capa de persistencia](persistencia.md) del Laboratorio 3: los servicios de acá
orquestan sus repositorios, nunca escriben SQL y nunca saben que existe HTTP.

### Equivalencias del enunciado

El enunciado está redactado para Java 21 + Spring Boot. El equipo tiene autorización para un stack
alternativo ([ADR-001](adr/ADR-001-eleccion-del-stack.md)); estas son las equivalencias que se
aplicaron, para que cada punto de la rúbrica se pueda ubicar sin ambigüedad:

| Enunciado | En este proyecto |
|---|---|
| `@Transactional` | Un único `sesion.commit()` en el servicio; el repositorio nunca confirma |
| Bean Validation | `pydantic.Field(...)` en los DTOs de entrada (`presentation/schemas.py`) |
| *Records* de entrada y salida | `@dataclass(frozen=True)` en `business/` y modelos Pydantic en `presentation/` |
| MapStruct | Mapeo manual explícito en el router (`_respuesta()`) |
| Mockito | Dobles de prueba escritos a mano sobre SQLite en memoria (ver § 7.2) |
| JaCoCo | `coverage` sobre `src/app/business` |
| `extends RuntimeException` | `class ErrorDeNegocio(Exception)` y su jerarquía |

---

## 1 · Qué compone la capa

```
src/app/business/
├── errors.py                     violaciones del dominio, sin una sola referencia a HTTP
├── parsers/
│   └── comprobante_bac.py        lee la notificación bancaria y le pone una confianza
└── services/
    ├── categoria_service.py      jerarquía de clasificación del titular
    ├── comercio_service.py       catálogo compartido y categoría sugerida por titular
    ├── metodo_pago_service.py    la llave de emparejamiento de la ingesta
    ├── presupuesto_service.py    límite, consumo y umbral de alerta
    ├── regla_categorizacion_service.py   las reglas que afinan la clasificación
    ├── categorizacion.py         la cadena de categorización, que los dos procesos comparten
    ├── tipo_cambio_service.py    tasa de referencia del BCCR, con respaldo
    ├── registrar_compra_service.py   Proceso 1 · captura manual con desglose
    ├── conciliacion_service.py   Proceso 2 · la transacción de cinco tablas
    ├── compra_service.py         lecturas de Compra (no escribe)
    └── bitacora_service.py       trazabilidad en MongoDB, fuera de la transacción
```

Tres decisiones sostienen la frontera, porque Python no la impone por sí solo:

1. **El servicio recibe una orden propia, no un modelo de la API.** `CrearCategoriaComando`,
   `CrearMetodoPagoComando` y `CrearReglaComando` son dataclasses de `business/`. Si el servicio
   recibiera un `BaseModel` de FastAPI, el dominio quedaría amarrado a la forma del contrato HTTP.
2. **El repositorio nunca confirma.** Solo agrega y consulta; el `commit` lo hace el servicio, que
   es el único que sabe si la operación de negocio completa terminó bien. Ese límite es el que
   hace posible la transacción de cinco tablas de la § 3.
3. **Los errores de negocio son excepciones propias.** Ninguna menciona HTTP; `main.py` es el único
   archivo autorizado a traducirlas (§ 5).

---

## 2 · Los procesos

### 2.1 · Proceso 2 · Ingesta y conciliación de un comprobante *(transaccional)*

Es el proceso multi-paso, y el que se prueba con *rollback*. Implementa los pasos 4 a 9 del
[Proceso 2 de la propuesta](propuesta-dominio.md#proceso-2--ingesta-y-conciliación-de-un-comprobante-de-correo-transaccional).
Los pasos 1 a 3 -leer el correo, guardar el `Comprobante`, parsearlo- ocurren antes y no son parte
de esta transacción: para cuando `ConciliacionService.conciliar` recibe el control, el comprobante
ya existe en la base y ya viene parseado.

**Entrada:** `usuario_id`, el `Comprobante` ya guardado y un `ComprobanteParseado`.
**Salida:** `ResultadoConciliacion(compra_id, requiere_revision, presupuesto_alertado)`, o `None`.

| Paso | Qué hace |
|---|---|
| 0 | **Puerta de entrada.** Si el comprobante no es una compra, no es confiable, o le falta comercio, monto, moneda o fecha, devuelve `None`: queda para revisión manual y no se inventa nada |
| 4 | Empareja el `MetodoPago` del titular por los últimos cuatro dígitos. Nunca crea uno |
| 5 | Resuelve el `Comercio` por su nombre normalizado -y lo crea si es la primera vez que se ve |
| 6 | Categoriza: primero las reglas activas del titular por prioridad, si ninguna coincide la categoría que ese titular le asignó a ese comercio |
| 6b | Si la moneda no es la base, convierte con la tasa de la fecha de la compra |
| 6c | Crea la `Compra` y su única `LineaCompra` por el monto total |
| 7 | Sube `veces_aplicada` de la regla que acertó, si hubo alguna |
| 8 | Acumula `Presupuesto.monto_consumido` y decide si esta compra cruzó el umbral de alerta |
| 9 | Deja el `Comprobante` ligado a su compra (`compra_id`) |
| — | **Un solo `commit`**, y recién después se escribe la bitácora en MongoDB |

#### Reglas

| Regla | Dónde |
|---|---|
| Bajo 0.75 de confianza el comprobante no se convierte en compra solo | `ComprobanteParseado.es_confiable` |
| Una anulación o un reverso no son gasto: no concilian | `ComprobanteParseado.es_compra` |
| Si los últimos cuatro no casan con ninguna tarjeta, la compra se crea igual pero marcada para revisión -puede ser una tarjeta que el titular todavía no registró | `metodo_pago is None` → `requiere_revision` |
| Nunca se inventa un método de pago: sin coincidencia exacta, ninguno | `buscar_por_ultimos_cuatro` |
| Una moneda que el sistema no reconoce no concilia: no se inventa a qué tasa vale | `Moneda.__members__` |
| Las reglas se evalúan por prioridad ascendente y **gana la primera que coincide** | `_categorizar` |
| Si el comercio no tiene categoría, la compra queda sin clasificar y marcada para revisión | `categoria_id is None` → `requiere_revision` |
| El presupuesto solo acumula si está en la **misma moneda** que la compra: mezclar monedas en una suma daría un número inventado | `presupuesto.moneda == moneda` |
| La alerta de umbral se dispara una sola vez: solo si antes de esta compra el consumo estaba por debajo del umbral | `porcentaje_antes < umbral_alerta` |
| Si el proveedor de tipo de cambio no responde, se usa tasa 1 -mejor un total sin convertir que perder el gasto | `_tasa_de_conversion` |
| La bitácora nunca puede hacer fallar la conciliación | § 3.3 |

#### Cálculos

| Cálculo | Fórmula | Nota |
|---|---|---|
| Confianza del parseo | `campos_obligatorios_encontrados / 4` | Los cuatro son comercio, fecha, últimos cuatro y monto |
| Total de la compra | `monto del comprobante` | La notificación trae el total con impuesto incluido; `impuesto_desglosado = false` |
| Tasa aplicada | tasa de **venta** del BCCR de la fecha de la compra, o `1` | Se guarda copiada en `Compra.tipo_cambio_aplicado`, no como referencia -corregir una tasa mal cargada no puede cambiar retroactivamente un gasto ya cerrado |
| Total en moneda base | `total × tipo_cambio_aplicado`, redondeado a 2 decimales con `ROUND_HALF_UP` | Todo en `Decimal`: con punto flotante un reporte de gastos no cuadra por céntimos |
| Consumo de presupuesto | `monto_consumido += total` | En la moneda del presupuesto, que debe ser la de la compra |
| Porcentaje usado | `monto_consumido / monto_limite × 100` | `PresupuestoService.calcular_estado`, función pura |
| Estado del presupuesto | `> 100` → `EXCEDIDO`; `>= umbral` → `CERCA_DEL_LIMITE`; si no `EN_RANGO` | |

#### Validaciones de la corrección manual

`resolver_revision` corrige a mano el método de pago y/o la categoría de una compra que quedó
marcada para revisión:

- Corregir «nada» no es una corrección: si no viene ni método de pago ni categoría → `DatosInvalidos`.
- La compra, el método de pago y la categoría tienen que **pertenecer al titular** → `RecursoNoEncontrado`.
  Es la validación que impide tocar datos de otra cuenta pasando un id ajeno.
- Un método de pago desactivado no se puede asignar → `ReglaDeNegocioViolada`.
- Solo se clasifica en categorías **hoja**: las padre totalizan, no reciben gasto → `ReglaDeNegocioViolada`.
- Si la compra **ya tenía** categoría y se manda otra, se corrige el dato pero **no se toca ningún
  presupuesto**: mover el gasto de un presupuesto a otro exigiría revertir lo ya acumulado en el
  anterior, que es una operación aparte que esto no cubre. Solo se acumula cuando la categoría
  estaba vacía, porque ese gasto todavía no había impactado nada.

---

### 2.2 · Proceso 1 · Registro de una compra con desglose y categorización

El proceso que el titular ejecuta a mano cuando la compra no llegó por correo: un tiquete de papel,
una compra en efectivo, una factura que el banco no notificó. Lo implementa
`RegistrarCompraService.registrar`, y lo expone `POST /api/compras`.

A diferencia del Proceso 2, acá **sí hay desglose real**: varios renglones, cada uno con su
cantidad, su precio unitario, su descuento y su propia categoría, y el impuesto se calcula en vez
de venir incluido en un total opaco. Es la diferencia que impone el dominio: una compra que entra
por correo nace con un solo renglón porque la notificación bancaria
*«[nunca trae el detalle de qué se compró](propuesta-dominio.md#qué-traen-realmente-los-comprobantes)»*.

**Entrada:** `RegistrarCompraComando`, con una tupla de `LineaDeCompraComando`.
**Salida:** `CompraRegistrada`, con el desglose calculado y los presupuestos que se alertaron.

| Paso | Qué hace |
|---|---|
| 1 | El titular escoge comercio, método de pago, fecha y moneda |
| 2 | Agrega uno o más renglones: descripción, cantidad, precio unitario, descuento y si es exento |
| 3 | Para cada renglón sin categoría, el sistema la sugiere: regla del titular por prioridad, si ninguna coincide la del comercio |
| 4 | La categoría que el titular indicó **gana** sobre cualquier regla -corregir es lo que hace aprender al sistema |
| 5 | Calcula el desglose: subtotal e impuesto por renglón, y los totales de la compra |
| 6 | Si el titular transcribió el total del recibo, valida el cuadre |
| 7 | La compra queda `REGISTRADA` e impacta el presupuesto de cada categoría afectada |
| — | **Un solo `commit`** para las cuatro tablas, y recién después la bitácora |

#### Reglas

| Regla | Dónde |
|---|---|
| Una compra `REGISTRADA` no admite renglones sin categoría: si se permitiera, los reportes mostrarían menos gasto del real | `_resolver_categoria` |
| Solo se clasifica en categorías **hoja**: las padre totalizan, no reciben gasto directo | `_categoria_del_titular` |
| La categoría que eligió el titular gana sobre la que sugeriría una regla | `_resolver_categoria` |
| Las reglas se evalúan por prioridad ascendente y gana la primera que coincide | `categorizacion.primera_regla_que_coincide` |
| Dos renglones categorizados por la misma regla son **una sola** aplicación de esa regla | el conjunto de reglas antes de subir `veces_aplicada` |
| El comercio, el método de pago y cada categoría tienen que existir, estar activos y **pertenecer al titular** | `_resolver_metodo_pago`, `_categoria_del_titular` |
| Un método de pago desactivado no se puede usar -pero el histórico que lo usó no se toca | `_resolver_metodo_pago` |
| El presupuesto solo acumula si está en la misma moneda que la compra | `_acumular_presupuestos` |
| La alerta de umbral se dispara una sola vez, al cruzarlo | `_acumular_presupuestos` |

#### Cálculos

| Cálculo | Fórmula |
|---|---|
| Subtotal de renglón | `redondear(cantidad × precio_unitario − descuento_renglón)` |
| Impuesto de renglón | `0` si es exento, si no `redondear(subtotal × 13 %)` |
| Subtotal de compra | suma de los subtotales de renglón |
| Impuesto de compra | suma de los impuestos de renglón |
| Total de compra | `subtotal − descuento_global + impuesto` |
| Total en moneda base | `redondear(total × tipo_cambio_aplicado)` |
| Impacto en el presupuesto de una categoría | suma de `subtotal + impuesto` de **sus** renglones |

Todo redondeado a dos decimales con `ROUND_HALF_UP` sobre `Decimal`. Las tres primeras fórmulas
son además `CHECK` en la base (`V3`), así que un error de cálculo acá no pasaría del `INSERT`.

**El descuento global no se prorratea** entre renglones: se resta después de sumar, para que el
titular vea de dónde salió la rebaja. La consecuencia es que lo que impacta a los presupuestos
corresponde al total *antes* de ese descuento; prorratearlo exigiría una regla de reparto que el
dominio no define, y asumir una sería inventarla.

#### Validaciones

- La fecha no puede ser futura.
- La compra debe tener al menos un renglón.
- La cantidad debe ser mayor que cero y el precio unitario no puede ser negativo.
- Ningún descuento puede superar el monto sobre el que se aplica -ni el del renglón sobre
  `cantidad × precio_unitario`, ni el global sobre el subtotal.
- Si se declaró el total del recibo, la diferencia contra el calculado no puede pasar de **un
  colón**. El declarado nunca se usa como total: se compara. Si se usara, un renglón mal digitado
  quedaría escondido detrás de un total correcto y el desglose por categoría -que es para lo que
  sirve capturar a mano- mentiría.
- Una compra en la moneda base no lleva conversión; una en otra moneda exige la tasa **de su
  fecha**, que llega en el comando. No se usa la de hoy: el titular puede estar capturando una
  compra de hace meses, y esa no es la que pagó.

#### La otra mitad: corregir lo ya registrado

El paso 4 del proceso -«si corrige, el sistema le ofrece crear la regla»- va más allá de la captura,
porque también aplica a lo que ya entró por correo:

| Paso | Dónde vive |
|---|---|
| El titular corrige la categoría o el método de pago de una compra | `ConciliacionService.resolver_revision` |
| **Corregir crea la regla** | `ComercioService.asignar_categoria` + `ReglaCategorizacionService.crear` |
| Y corrige también lo que ya pasó | `ConciliacionService.recategorizar_compras_de_comercio` |

---

## 3 · La garantía transaccional

### 3.1 · Qué se escribe, y por qué tiene que ser atómico

**Los dos procesos son transaccionales.** `ConciliacionService.conciliar` escribe en **cinco
tablas**; `RegistrarCompraService.registrar` en **cuatro** -las mismas menos `comprobante`, porque
una compra capturada a mano no nació de ningún correo:

| Tabla | Qué escribe | Proceso 2 | Proceso 1 |
|---|---|:---:|:---:|
| `compra` | La compra nueva | ✓ | ✓ |
| `linea_compra` | Su único renglón · todos los del desglose | ✓ | ✓ |
| `regla_categorizacion` | `veces_aplicada += 1` de la regla que acertó | ✓ | ✓ |
| `presupuesto` | `monto_consumido += …` de cada categoría afectada | ✓ | ✓ |
| `comprobante` | `compra_id`, que lo marca como conciliado | ✓ | — |

Si el paso del presupuesto fallara a mitad de camino, quedaría una compra creada que nunca impactó
el avance mensual: el titular vería el gasto en su lista pero no en su presupuesto, y no habría
forma de detectar la inconsistencia salvo cuadrando a mano compra por compra.

En el Proceso 2 es peor todavía, y por eso es el que se prueba con *rollback*: como el comprobante
ya quedaría ligado a una compra, un reintento no lo volvería a tomar y la inconsistencia sería
**permanente**.

### 3.2 · Cómo se implementa

No hay anotación: hay **un solo `commit`**, al final del método, y ningún repositorio confirma por
su cuenta. Todas las escrituras anteriores quedan pendientes en la misma `Session` de SQLAlchemy;
cualquier excepción entre medio sale del servicio sin haber confirmado, la sesión se descarta al
cerrarse la petición y la transacción se revierte entera.

El `flush` que hace `CompraRepository.agregar` **no** confirma: solo empuja el `INSERT` para que
`compra.id` exista y `LineaCompra` pueda apuntarle. Sigue dentro de la misma transacción.

### 3.3 · Lo que queda deliberadamente afuera

Dos escrituras **no** son parte de la transacción, y las dos por una razón explícita:

**El `Comercio`.** `ComercioService.resolver_o_crear` confirma con su propio `commit`. El catálogo
de comercios es compartido entre todos los titulares, y crear uno nuevo no es parte de conciliar el
comprobante de nadie en particular: en el Proceso 2 del dominio, *«se resuelve el Comercio»* es un
paso **previo** a *«se crea la Compra»*. Si la conciliación se revirtiera, el comercio
recién descubierto sigue siendo un comercio real que existe.

**La bitácora de MongoDB.** Se escribe **después** de confirmar en PostgreSQL, y nunca puede hacer
fallar la conciliación: `BitacoraRepository` se traga cualquier fallo de conexión o de escritura y
devuelve `False` en vez de propagarlo. Es el trade-off que documenta
[ADR-002](adr/ADR-002-subdominio-documental-en-mongodb.md): la bitácora **explica** lo que pasó, no
lo **decide**. Ningún total ni ningún saldo del sistema depende de ella, así que perder un evento
de trazabilidad es preferible a perder el gasto.

### 3.4 · Cómo se prueba

`tests/integracion/test_rollback_conciliacion.py` corre contra un `postgres:16-alpine` real
levantado con Testcontainers y provoca el fallo **dentro** del servicio, con
`unittest.mock.patch.object` sobre el repositorio del paso que se quiere romper. No ensucia la base
ni toca el código del servicio: el que corre es `ConciliacionService` sin modificar.

| Prueba | Qué verifica |
|---|---|
| `test_un_fallo_al_acumular_el_presupuesto_no_deja_nada_escrito` | El caso del § 3.1. Cuando el paso 8 revienta, la `Compra`, su `LineaCompra`, el contador de la regla y el `comprobante.compra_id` ya estaban escritos -y después del `ROLLBACK` no queda **ninguno** |
| `test_el_comercio_resuelto_sobrevive_al_rollback` | La excepción deliberada del § 3.3: el comercio que se creó en el paso 5 sigue existiendo, pero la compra no. Fija la decisión para que un cambio futuro que meta el catálogo dentro de la transacción se note acá y no en producción |
| `test_un_fallo_al_escribir_el_renglon_no_deja_la_compra_suelta` | Que `flush` no sea `commit`: la `Compra` que ya recibió su id tampoco sobrevive |
| `test_una_conciliacion_completa_si_escribe_las_cinco_tablas` | El contraste que le da sentido a las tres anteriores: sin fallo provocado, las cinco escrituras sí quedan. Sin esta, «no quedó nada» pasaría por el motivo equivocado |

Además, `tests/integracion/test_esquema_postgres.py::test_una_transaccion_fallida_no_deja_nada_a_medias`
verifica el mecanismo del motor -dos escrituras pendientes, una viola una restricción al confirmar,
y el `ROLLBACK` deshace las dos-, que es de lo que esta garantía depende por debajo.

---

## 4 · La frontera de DTOs

### 4.1 · De entrada

Dos capas de validación, con responsabilidades separadas a propósito:

**Forma del dato → `presentation/schemas.py`.** Tipos, largos, rangos y formato, con
`pydantic.Field`. Un valor mal formado nunca llega al servicio: FastAPI responde 422 antes.

```python
class CrearMetodoPagoRequest(BaseModel):
    usuario_id: int = Field(gt=0, le=_ID_MAXIMO)
    alias: str = Field(min_length=1, max_length=60, examples=["Visa BAC"])
    tipo: TipoMetodoPago
    ultimos_cuatro: str | None = Field(default=None, min_length=4, max_length=4)
    dia_corte: int | None = Field(default=None, ge=1, le=31)
```

**Regla del dominio → el servicio.** Que solo débito y crédito lleven últimos cuatro, que no haya
dos tarjetas del mismo titular terminadas en los mismos cuatro dígitos, o que el día de corte solo
aplique a una tarjeta de crédito, son preguntas del negocio: cambian sin que el contrato HTTP
cambie, y tienen que seguir valiendo si mañana el servicio se llama desde un script.

El servicio recibe una **orden propia**, nunca el modelo de Pydantic:

```python
@dataclass(frozen=True)
class CrearMetodoPagoComando:
    usuario_id: int
    alias: str
    tipo: TipoMetodoPago
    moneda: Moneda = Moneda.CRC
    ultimos_cuatro: str | None = None
    entidad: str | None = None
    dia_corte: int | None = None
```

El router traduce `Request` → `Comando` explícitamente. Es el mapeo manual que el enunciado admite
como alternativa a MapStruct.

### 4.2 · De salida

Los DTOs de salida del negocio son dataclasses inmutables de `business/`:

| DTO | Servicio | Qué resuelve |
|---|---|---|
| `CompraRegistrada` · `LineaRegistrada` | `RegistrarCompraService` | La compra capturada, con su desglose calculado y los presupuestos alertados |
| `ResultadoConciliacion` | `ConciliacionService` | `compra_id`, `requiere_revision`, `presupuesto_alertado` |
| `CompraDetallada` | `CompraService` | La compra con los nombres de comercio, método de pago y categoría ya resueltos |
| `EstadoDePresupuesto` | `PresupuestoService` | Límite y consumo con el porcentaje y el estado calculados |
| `ComercioClasificado` · `MovimientoDetallado` | `ComercioService` | Agrupación y detalle de movimientos |
| `ComprobanteParseado` | `parsers/comprobante_bac` | Resultado de lectura, no una entidad: no se guarda tal cual |

El router los convierte a su `*Response` de Pydantic con una función explícita
(`_respuesta_registrada()` y `_respuesta()` en `routers/compras.py`), así que **ninguna entidad del
ORM sale de la aplicación**.

Los **dos procesos** cumplen la frontera entera, que es lo que pide el criterio: entran por un
comando propio y salen por un DTO propio.

| Proceso | Entrada | Salida |
|---|---|---|
| 1 · Registro con desglose | `RegistrarCompraComando` + `LineaDeCompraComando` | `CompraRegistrada` + `LineaRegistrada` |
| 2 · Conciliación | `Comprobante` + `ComprobanteParseado` | `ResultadoConciliacion` |

### 4.3 · Dónde la frontera todavía no es estricta

Fuera de los dos procesos, cinco métodos de los servicios de catálogo devuelven la entidad del ORM
al router en vez de un DTO propio:

| Método | Devuelve |
|---|---|
| `CategoriaService.crear` | `Categoria` |
| `MetodoPagoService.crear` · `desactivar` | `MetodoPago` |
| `PresupuestoService.crear_o_actualizar` | `Presupuesto` |
| `ReglaCategorizacionService.crear` · `desactivar` | `ReglaCategorizacion` |
| `ConciliacionService.resolver_revision` | `Compra` |

El router la convierte a su `*Response` antes de responder, así que la entidad no cruza hacia el
cliente ni se serializa nunca. Pero sí cruza de negocio a presentación, y la regla que el equipo se
puso es que no debería. Es deuda consciente y acotada: son operaciones de catálogo, no los procesos
del dominio, y el patrón correcto ya existe en el mismo código -`CompraRegistrada` y
`CompraDetallada` son exactamente eso- así que replicarlo es mecánico. Ver § 8.

---

## 5 · Excepciones del dominio

Ninguna menciona HTTP. `main.py` es el único archivo autorizado a traducirlas, y por eso el mismo
servicio se puede llamar desde un script o una tarea programada sin arrastrar el protocolo.

| Excepción | Cuándo | HTTP |
|---|---|---|
| `ErrorDeNegocio` | Raíz de la jerarquía; no se lanza directamente | — |
| `DatosInvalidos` | El dato tiene la forma correcta pero no cumple una regla del dominio | 422 |
| `RecursoNoEncontrado` | Se referenció algo que no existe **o que no pertenece al titular** | 404 |
| `ReglaDeNegocioViolada` | La operación choca con el estado actual del sistema | 409 |
| `ErrorDeProveedorExterno` | El Banco Central rechazó la solicitud o no respondió | 502 |

Dos decisiones que vale la pena justificar:

- **`RecursoNoEncontrado` para lo ajeno.** Pedir la compra de otra persona responde 404, no 403.
  Confirmar que algo existe pero no es tuyo le dice a quien pregunta más de lo que debería.
- **`ErrorDeProveedorExterno` se distingue del resto** para que se traduzca a 502 y no a un 4xx.
  Que el BCCR esté caído no significa que el cliente se haya equivocado, y un 4xx le diría
  exactamente eso.

---

## 6 · Patrones de diseño aplicados

### 6.1 · Cadena de responsabilidad — la categorización

**La señal que lo justificaba.** Decidir la categoría de una compra tiene tres fuentes posibles, con
una prioridad clara entre ellas: las reglas del titular primero, la categoría que ese titular le
asignó al comercio después, y si ninguna aplica, ninguna. Escrito como condicionales anidados, el
método crece un nivel de anidamiento por cada fuente nueva, y agregar una cuarta -una categoría
sugerida global del comercio, por ejemplo- obliga a reabrir el bloque y reordenar los `elif` sin
romper la precedencia de los anteriores.

**Justificación.** Cada eslabón resuelve la categoría o le pasa la decisión al siguiente, de modo
que la precedencia queda expresada por el orden de la cadena y no por la forma del condicional, y
una fuente nueva se agrega sin tocar las que ya estaban.

El primer eslabón vive en `services/categorizacion.py`, como función pura, porque **los dos procesos
lo comparten**: que la misma compra caiga en una categoría distinta según si entró por correo o se
capturó a mano sería un error que nadie notaría hasta cuadrar un reporte a mano.

```python
def primera_regla_que_coincide(reglas, comercio_normalizado):
    """La primera regla cuyo patrón está contenido en el nombre normalizado del comercio."""
    for regla in reglas:
        if regla.patron.upper() in comercio_normalizado:
            return regla
    return None
```

Y así se encadena en la conciliación (el registro manual hace lo mismo, por renglón):

```python
categoria_id, regla_aplicada = self._categorizar(usuario_id, comercio.nombre_normalizado)
if categoria_id is None:
    categoria_id = self.comercios_servicio.categoria_sugerida_para(usuario_id, comercio.id)
```

La cadena interna -las reglas entre sí- se ordena por `prioridad` ascendente y gana la primera que
coincide, que es lo que permite poner excepciones específicas antes que las generales. Por eso
`ReglaCategorizacionService` rechaza dos reglas con la misma prioridad: un empate haría la cadena no
determinista.

Los dos procesos difieren en un eslabón, y a propósito: en el registro manual, la categoría que el
titular indicó se evalúa **antes** que cualquier regla. Corregir es justamente lo que hace aprender
al sistema, así que una regla que él mismo creó antes no puede pisar su decisión de ahora.

**Segunda instancia del mismo patrón**, en otro servicio: `TipoCambioService._consultar` pregunta
primero al Banco Central y, si no hay credenciales o el servicio no responde, cae al respaldo del
Ministerio de Hacienda; si los dos fallan, el error explica qué pasó con **cada uno**, porque son
dos causas muy distintas -falta suscribirse, o el proveedor está caído- y un mensaje genérico no
dejaría saber cuál es.

### 6.2 · Comando — la frontera del dominio

**La señal que lo justificaba.** La forma natural de que un router llame a un servicio es pasarle el
modelo de Pydantic que ya recibió. Hacerlo habría amarrado el negocio al contrato HTTP: cambiar el
nombre de un campo en la API obligaría a tocar el servicio, y el servicio dejaría de poder llamarse
desde un script, una tarea programada o una prueba sin construir un objeto de FastAPI. La señal
concreta apareció con `CrearMetodoPagoRequest`, que tiene siete campos de los cuales tres son
opcionales: pasarlos sueltos como argumentos posicionales era ilegible, y pasar el modelo entero
era romper la frontera.

**Justificación.** La orden viaja como un objeto inmutable propio del dominio, de modo que el
servicio depende de una estructura que él mismo define y el contrato HTTP puede cambiar sin tocar
una sola regla de negocio.

```python
@dataclass(frozen=True)
class CrearReglaComando:
    """Orden que recibe el negocio para crear una regla de categorización."""

    usuario_id: int
    nombre: str
    patron: str
    categoria_destino_id: int
    campo: CampoRegla = CampoRegla.COMERCIO_NORMALIZADO
    prioridad: int | None = None
```

Cuatro instancias: `CrearCategoriaComando`, `CrearMetodoPagoComando`, `CrearReglaComando` y
`RegistrarCompraComando` -esta última compuesta, porque lleva adentro una tupla de
`LineaDeCompraComando`: la orden de registrar una compra incluye la de cada renglón.

`frozen=True` no es decorativo: una orden que el servicio pudiera modificar a mitad de camino
dejaría de ser una orden. En `RegistrarCompraComando` además es lo que permite calcular los
totales, validar el cuadre contra el recibo y recién entonces escribir, sabiendo que lo que se
escribe es lo mismo que se calculó.

### 6.3 · Otros dos que el código aplica

No se desarrollan acá porque el enunciado pide dos, pero conviene dejarlos anotados:

- **Fábrica / raíz de composición** — `presentation/dependencies.py`. Cada `obtener_servicio_de_*`
  arma un servicio con sus repositorios sobre la sesión de *esta* petición. Los routers reciben el
  servicio ya construido y nunca tocan la base. Es el único punto donde presentación conoce a
  `data/`, y es un candidato natural a mudarse a `config/` para que la regla quede sin excepciones.
- **Objeto nulo** — `BitacoraRepository(None)` y `TipoCambioService | None`. En vez de que cada
  llamador pregunte «¿hay Mongo?» o «¿hay tipo de cambio?», el colaborador ausente se comporta como
  un no-op: la bitácora devuelve `False` y la conversión usa tasa `1`. Es lo que permite que la
  conciliación funcione igual en un ambiente sin Mongo y sin credenciales del BCCR.

---

## 7 · Cómo se prueba

### 7.1 · Pruebas unitarias de las reglas

Corren sobre SQLite en memoria: sin archivos, sin red, sin infraestructura, y cada prueba arranca
con la base vacía.

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `tests/test_registrar_compra_service.py` | 31 | Cada regla, validación y cálculo del Proceso 1 |
| `tests/test_conciliacion_service.py` | 23 | Cada regla y cálculo del Proceso 2 |
| `tests/test_comercio_service.py` | 19 | Normalización, resolución del catálogo, categoría sugerida |
| `tests/test_presupuesto_service.py` | 16 | Límite, umbral, las tres franjas de estado |
| `tests/test_regla_categorizacion_service.py` | 12 | Prioridad sin empates, campo soportado, desactivación |
| `tests/test_categoria_service.py` | 11 | Nombre, color, jerarquía, siembra estándar |
| `tests/test_metodo_pago_service.py` | 10 | Últimos cuatro, duplicados, día de corte |
| **Total sobre las reglas** | **122** | El mínimo del enunciado son 8 |

La suite completa son **189** pruebas sobre SQLite más **14** de integración contra PostgreSQL real.

### 7.2 · Sobre los dobles de prueba

El enunciado pide Mockito. En Python el equivalente directo es `unittest.mock`, y se usa donde de
verdad hace falta simular:

- `tests/integracion/test_rollback_conciliacion.py` usa `unittest.mock.patch.object` sobre
  `PresupuestoRepository.buscar` y `LineaCompraRepository.agregar` para provocar el fallo en un
  paso concreto. Es el único modo de romper el proceso a mitad de camino sin tocar el código del
  servicio: el que corre es `ConciliacionService` sin modificar.

En el resto de las pruebas de reglas se usan **dobles escritos a mano** en vez de *mocks*, y eso sí
es una decisión que conviene explicar:

- `BitacoraComprasService(BitacoraRepository(None))` — una bitácora sin colección: cualquier
  llamada es un no-op. Es el mismo objeto nulo que usa la aplicación cuando Mongo no está
  configurado, así que la prueba ejercita un camino real y no una simulación.
- Un `TipoCambioService` falso que devuelve una tasa fija, para que la conversión de moneda se
  pueda verificar sin salir a la red.
- La sesión de SQLAlchemy **no** se simula: es SQLite en memoria de verdad. Un *mock* del
  repositorio verificaría que el servicio lo llamó, pero no que la transacción quede coherente,
  que es justamente lo que hay que probar.

Se aísla la regla sin aislar el ORM, porque el ORM es parte del comportamiento que estos servicios
garantizan.

### 7.3 · Pruebas de integración

En `tests/integracion/`, contra un `postgres:16-alpine` real levantado por la propia prueba con
Testcontainers: lo que SQLite no puede probar igual de bien -`NUMERIC` exacto, `ON DELETE CASCADE`
y `RESTRICT` reales, el largo real de un `VARCHAR`, ver [la capa de persistencia § 6](persistencia.md)-
y el *rollback* de los procesos (§ 3.4).

### 7.4 · Cobertura

```bash
pytest -m "not integracion" --cov --cov-report=term-missing
```

Mide solo `src/app/business`, que es donde viven las reglas: que un router o un modelo de
SQLAlchemy estén cubiertos no dice nada sobre si una regla de negocio tiene prueba, y promediarlos
escondería justo lo que importa.

**Cobertura actual: 93.07 %**, con el umbral en 70 % (`fail_under` en `pyproject.toml`). El CI la
mide en el mismo paso que corre las pruebas, así que si baja del umbral el paso falla igual que si
se rompiera una prueba -el reporte no es informativo, es una condición.

Se deja el umbral en 70 y no en el valor real para que agregar una rama sin prueba avise, sin que
cada línea nueva rompa el CI por un punto decimal. El archivo más bajo es `compra_service.py`
(80 %): son lecturas, no reglas -lo que de verdad importa que esté cubierto son los dos procesos,
en 94 % y 95 %.

---

## 8 · Lo que queda abierto

Declararlo es parte de la entrega: lo que no se dice, se encuentra.

1. **El mapeo todavía no conoce cuatro columnas obligatorias del esquema.** Aplicando `V1`–`V7`
   sobre una base limpia, las 14 tablas y todas las columnas que el mapeo usa existen -eso se
   cerró en esta entrega-, pero queda la dirección contraria: `comprobante` exige `usuario_id`,
   `remitente` y `recibido_en`, y `linea_compra` exige `usuario_id`, y ninguna de las cuatro está
   mapeada. La aplicación crea su esquema con `Base.metadata.create_all()`, así que hoy no lo
   nota; apuntarla a una base migrada con Flyway fallaría al insertar. Es la otra mitad de la
   observación del Laboratorio 3 y se arrastra desde ahí: cerrarla es mapear esas columnas
   (y rellenar `linea_compra.usuario_id` en las filas que ya existen), no una migración nueva.
2. **La aplicación sigue creando su esquema con `create_all()`**, no con Flyway. Las migraciones
   son la fuente de verdad documentada del modelo, pero todavía no son la que la app aplica al
   arrancar; mientras las dos coexistan, nada impide que vuelvan a separarse.
3. **Cinco métodos de los servicios de catálogo devuelven la entidad del ORM** al router en vez de
   un DTO propio (§ 4.3). Los dos procesos del dominio sí cumplen la frontera entera.
4. **El armado de servicios vive en `presentation/`** (§ 6.3). Es un *composition root* legítimo,
   pero es la única excepción a la regla de que presentación no conoce a `data/`.
5. **El desglose manual no tiene pantalla todavía.** `POST /api/compras` existe y está probado,
   pero el frontend aún no lo consume: por ahora el Proceso 1 se ejecuta desde la API.
6. **El descuento global no se reparte entre presupuestos** (§ 2.2). Prorratearlo exigiría una
   regla de reparto que el dominio no define.

### Lo que sí se cerró en esta entrega

- El Proceso 1 pasó de estar implementado a medias a ser un servicio completo con su endpoint.
- La prueba de *rollback* ahora ejerce `ConciliacionService` con un fallo provocado adentro,
  no solo el mecanismo del motor.
- La cobertura se mide en el CI con umbral, y falla el paso si baja de 70 %.
- `V6` y `V7` traen a Flyway los cambios de esquema que hasta ahora solo existían porque la
  aplicación corría `create_all()`: `comercio_categoria_sugerida`, las columnas del parseo en
  `comprobante`, `transferencia_sinpe` y las columnas nuevas de `usuario`.

---

## Documentos relacionados

| Documento | Qué contiene |
|---|---|
| [Propuesta de dominio](propuesta-dominio.md) | El negocio, las entidades y los dos procesos con sus reglas |
| [Capa de persistencia](persistencia.md) | Mapeo ORM, repositorios, N+1 y consultas de negocio |
| [Modelo de datos](modelo-de-datos.md) | El esquema relacional y el subdominio documental |
| [Arquitectura](arquitectura.md) | Diagramas de capas, recorrido de una petición y despliegue |
| [ADR-001](adr/ADR-001-eleccion-del-stack.md) | Por qué Python + FastAPI en lugar de Java + Spring Boot |
| [ADR-002](adr/ADR-002-subdominio-documental-en-mongodb.md) | Por qué la bitácora vive en MongoDB y fuera de la transacción |
