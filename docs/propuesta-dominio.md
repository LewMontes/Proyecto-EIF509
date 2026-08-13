# Propuesta de Dominio · Gastonomo

**Laboratorio 1 · EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026 · Grupo G01**

---

## 1 · Identificación

### Equipo y sistema

|                       |                                                             |
|-----------------------|-------------------------------------------------------------|
| **Sistema propuesto** | **Gastonomo** — control de gastos personales por categorías |
| **Integrantes**       | Jose Alexis Solís Carvajal · carné               |
|        |    Luis Antonio Montes de Oca Ruiz · carné 191862                      |

---

## 2 · El negocio

### Descripción del negocio

Una persona de clase media en Costa Rica hace entre 60 y 120 compras al mes repartidas entre
supermercados, farmacias, gasolineras, sodas, suscripciones en dólares y SINPE Móvil. Cada compra
deja un rastro distinto: un tiquete de papel, un correo del banco, una factura electrónica, una
notificación de la app. El resultado es que **nadie sabe realmente en qué se le va la plata**,
aunque toda la información exista.

Las herramientas actuales fallan en dos puntos. Las apps internacionales no entienden colones, ni
SINPE, ni los comercios locales. Y las hojas de cálculo caseras exigen digitar
todo a mano, así que se abandonan a las tres semanas.

**Gastonomo** es un sistema web **multiusuario**: cualquier persona crea su cuenta, vincula el
buzón donde le llegan los comprobantes de compra, y el sistema clasifica su gasto por categoría
—automáticamente cuando puede, con su ayuda cuando no— mostrándole en vivo cuánto lleva contra el
presupuesto que se puso. Cada cuenta es individual y sus datos están aislados de las demás.

Su diferenciador es la **trazabilidad**: de cualquier total en pantalla se puede bajar hasta el
comprobante original que lo generó, pasando por el tipo de cambio y la regla de categorización que
se aplicaron.

El sistema no maneja dinero real ni ejecuta pagos. Solo observa, clasifica y explica el gasto que
ya ocurrió.

### Actores

Estos son los roles que se programarán como control de acceso más adelante en el curso:

| Actor | Qué hace en el sistema |
|---|---|
| **Titular** | Dueño de su cuenta y de sus datos. Se registra, vincula su correo, registra compras, define categorías, presupuestos y reglas, y consulta sus reportes. Es el actor principal. |
| **Administrador** | Gestiona el catálogo compartido de comercios y las tasas de cambio. No ve las compras de nadie. |
| **Servicio de ingesta** | Actor no humano: el proceso automático que lee los buzones vinculados y crea compras. Actúa siempre en nombre de un titular y solo puede crear, nunca modificar ni borrar. |

---

## 3 · Entidades de negocio

### Listado de entidades

**1 · Usuario** — Persona dueña de su cuenta. Datos: nombre completo, correo, hash de contraseña,
moneda preferida, estado, fecha de alta. Es la raíz de aislamiento del sistema: toda consulta se
filtra por usuario, de modo que cualquier persona pueda registrarse sin ver los datos de nadie más.

**2 · CuentaCorreo** — Buzón vinculado del que se leen los comprobantes. Datos: proveedor
(Gmail, Outlook), dirección, token de acceso y token de refresco cifrados, fecha de expiración del
token, fecha de la última sincronización, estado. Se separa de `Usuario` porque una persona puede
vincular más de un buzón (el personal y el del trabajo), porque los tokens caducan y hay que
renovarlos por su cuenta, y porque desvincular un correo no puede implicar borrar la cuenta.

**3 · Categoria** — Clasificación del gasto, jerárquica (Alimentación → Supermercado). Datos:
nombre, descripción, color para los gráficos, categoría padre, si es hoja, estado. Solo las
categorías hoja reciben gasto directo; las padre existen para totalizar. Al crear una cuenta se
siembra un catálogo estándar para que nadie arranque con una lista vacía.

**4 · Comercio** — Establecimiento donde se compró. Datos: nombre, nombre normalizado,
identificación tributaria, provincia y **categoría sugerida**. Se normaliza aparte porque el
nombre que llega en los comprobantes es sucio (`AUTOMERCADO #12 SAN PEDRO`) y hay que agrupar sus
variantes. La categoría sugerida es la pieza central de la clasificación automática: como el
comprobante solo trae el nombre del negocio, el comercio es la mejor señal disponible.

**5 · MetodoPago** — Medio con el que se pagó. Datos: alias, tipo (efectivo, débito, crédito,
SINPE Móvil, transferencia), moneda, **últimos cuatro dígitos**, entidad emisora, día de corte.
Los últimos cuatro dígitos no son un dato cosmético: son la **llave de emparejamiento** con la que
el sistema decide a cuál tarjeta del titular corresponde un cargo que llegó por correo. Solo se
guardan esos cuatro, nunca el número completo.

**6 · Compra** — Encabezado de una compra. Datos: fecha, descripción, moneda, estado
(borrador → registrada → conciliada → anulada), origen, subtotal, descuento, impuesto, total,
indicador de impuesto desglosado, tipo de cambio aplicado y total en moneda base. Los totales se
persisten calculados: un gasto histórico debe seguir mostrando lo que se pagó aunque después
cambie el IVA.

**7 · LineaCompra** — Renglón de una compra, con su propia categoría. Datos: descripción,
cantidad, precio unitario, descuento, si es exento, subtotal y si la categoría la puso una regla o
una persona. Ver más abajo *«Qué traen realmente los comprobantes»*: en las compras ingeridas por
correo nace una sola línea por el monto total, y el desglose es un refinamiento posterior.

**8 · Presupuesto** — Tope de gasto de una categoría para un mes. Datos: año, mes, monto límite,
monto consumido, moneda, umbral de alerta, estado. El consumido se acumula en vez de sumarse en
cada consulta porque el frontend lo muestra en vivo.

**9 · ReglaCategorizacion** — Regla que afina la clasificación automática más allá de la categoría
por defecto del comercio. Datos: nombre, campo evaluado, patrón, prioridad, estado, veces
aplicada. Nace de que el usuario corrija una categoría, no de que entre a una pantalla de
configuración.

**10 · Comprobante** — Registro del correo del que nació una compra. Datos: identificador del
mensaje, remitente, asunto, fecha de recepción, estado, intentos de procesamiento, motivo de
fallo. **No guarda el correo**: el sistema lee el mensaje, extrae los cuatro campos que necesita y
descarta el contenido. Lo que queda es la constancia de que ese mensaje ya se procesó —lo que hace
idempotente la ingesta— y la trazabilidad de qué correo originó cada compra.

**11 · TipoCambio** — Tasa de conversión de una moneda a la base, **por fecha**. Datos: moneda
origen, moneda destino, fecha, tasa, fuente. Es un histórico: una compra hecha en dólares el 3 de
marzo se convierte siempre con la tasa del 3 de marzo.

### Cómo se relacionan

- Un **Usuario** tiene muchas **CuentaCorreo**, **Categorias**, **MetodoPago**, **Presupuestos**, **ReglaCategorizacion**, **Compras** y **Comprobantes**.
- Una **Categoria** puede tener muchas **Categorias** hijas y pertenece a lo sumo a una **Categoria** padre.
- Un **Comercio** tiene una **Categoria** sugerida.
- Una **Compra** pertenece a un **Usuario**, ocurre en un **Comercio** y se paga con un **MetodoPago**.
- Una **Compra** tiene muchas **LineaCompra**; una **LineaCompra** pertenece a una sola **Compra**.
- Una **LineaCompra** se clasifica en una **Categoria** (nula solo mientras la compra está en borrador).
- Un **Presupuesto** aplica a una **Categoria** de un **Usuario** en un año y mes concretos.
- Una **ReglaCategorizacion** apunta a una **Categoria** destino.
- Un **Comprobante** llega por una **CuentaCorreo** y origina a lo sumo una **Compra**.
- Una **Compra** en moneda distinta a la base usa el **TipoCambio** de su fecha.

El diagrama entidad-relación está en [`docs/arquitectura.md`](arquitectura.md).

### Qué traen realmente los comprobantes

Este es el hecho que condiciona todo el diseño de la ingesta. Un correo de notificación bancaria
trae **cuatro campos y nada más**:

| Campo | Ejemplo | Para qué se usa |
|---|---|---|
| Monto total | `₡45.320,00` | Total de la compra, **con impuesto ya incluido** |
| Últimos 4 dígitos | `****6411` | Emparejar con el `MetodoPago` del titular |
| Comercio | `AUTOMERCADO #12` | Resolver el `Comercio` y de ahí la categoría sugerida |
| Fecha y hora | `03/03/2026 14:22` | Fecha de la compra y período presupuestario |

Ocasionalmente traen también el número de autorización, la moneda cuando no es colones, o el
saldo disponible. **Nunca traen el detalle de qué se compró.**

Tres consecuencias de diseño:

1. **La ingesta crea una sola línea.** Una compra que entra por correo nace con un único renglón
   por el monto total. El desglose por renglón deja de ser algo que el parser produce y pasa a ser
   un **refinamiento manual opcional**: el titular ve el cargo de ₡45.320 en Automercado y, si le
   importa, lo parte en 60 % Alimentación y 40 % Limpieza.
2. **El impuesto no se desglosa.** Como el total ya viene con IVA incluido y no sabemos qué parte
   era exenta, calcularlo hacia atrás daría un número que parece preciso y no lo es. Las compras
   ingeridas guardan el total y se marcan con `impuesto_desglosado = false`. El desglose real solo
   existe cuando el usuario captura la compra a mano o cuando llega una factura electrónica.
3. **`LineaCompra` sigue justificándose**, por tres vías: la captura manual sí desglosa, el usuario
   puede partir después un cargo ingerido, y las facturas electrónicas en XML sí traen renglones.

### Subdominio documental candidato

**No identificamos ninguno.** Todo lo que el sistema persiste tiene esquema fijo y se modela
completo en PostgreSQL.

La parte que a primera vista parecería documental —los comprobantes que llegan por correo, con un
formato distinto por cada comercio— **no se almacena**. El sistema lee el mensaje, le extrae los
cuatro campos que necesita (monto, últimos cuatro dígitos, comercio y fecha) y descarta el
contenido. De ese correo solo queda una fila en `Comprobante` con datos perfectamente
estructurados: identificador del mensaje, remitente, fecha y estado.

Es una decisión deliberada y tiene dos razones:

1. **Privacidad.** Guardar el cuerpo de los correos bancarios de una persona significa custodiar
   información financiera sensible que el sistema no necesita para funcionar. Lo que no se
   almacena no se puede filtrar.
2. **No aporta.** Una vez extraídos los cuatro campos, el correo original no responde ninguna
   pregunta que el usuario vaya a hacer. La trazabilidad que sí importa —qué mensaje originó qué
   compra— se resuelve con el identificador del mensaje, que es un campo de texto normal.

Guardar los comprobantes crudos solo para tener dónde usar una base documental sería justificar la
herramienta al revés: el almacenamiento se elige por la forma de los datos, no la forma de los
datos por el almacenamiento que uno quiera estrenar.

---

## 4 · Procesos de negocio

### Proceso 1 · Registro de una compra con desglose y categorización

Convierte un tiquete en un gasto clasificado. Es el proceso que el titular ejecuta a mano cuando
la compra no llegó por correo, o cuando quiere desglosar una que sí llegó.

**Pasos**

1. El titular escoge comercio, método de pago, fecha y moneda.
2. Agrega uno o más renglones: descripción, cantidad, precio unitario, descuento y si es exento.
3. El sistema sugiere categoría para cada renglón: primero busca una `ReglaCategorizacion` que
   coincida, y si ninguna aplica usa la categoría sugerida del comercio.
4. El titular confirma o corrige. **Si corrige, el sistema le ofrece crear la regla** para que las
   próximas compras en ese comercio vayan solas a la categoría correcta.
5. El sistema calcula el desglose y lo muestra en vivo.
6. Si la compra viene de un recibo, se valida el cuadre contra el total impreso.
7. La compra pasa a `REGISTRADA` y se impacta el presupuesto de cada categoría afectada.

**Reglas**

- Una compra en `BORRADOR` admite renglones sin categoría; una `REGISTRADA` no. Si se permitiera
  registrar renglones sin clasificar, los reportes mostrarían menos gasto del real.
- Una compra `CONCILIADA` no se puede editar, solo anular.
- Anular una compra devuelve su monto al presupuesto; nunca se borra físicamente.
- Solo se puede clasificar en categorías **hoja**. Las padre totalizan, no reciben gasto.
- Las reglas se evalúan por prioridad ascendente y **gana la primera que coincide**, para que el
  usuario pueda poner excepciones específicas antes que las generales.
- Una categoría con gasto asociado no se borra: se desactiva, para no romper el histórico.

**Cálculos**

| Cálculo | Fórmula |
|---|---|
| Subtotal de renglón | `cantidad × precio_unitario − descuento_renglón` |
| Impuesto de renglón | `0` si es exento, si no `subtotal × 13 %` |
| Subtotal de compra | suma de los subtotales de renglón |
| Total de compra | `subtotal − descuento_global + impuesto` |
| Total en moneda base | `total × tasa_de_la_fecha_de_la_compra` |

El descuento global no se prorratea entre renglones: se resta después de sumar, para que el
usuario vea de dónde salió la rebaja. Todo monto se maneja con decimales exactos y redondeo
comercial a dos decimales; con números de punto flotante `0.1 + 0.2` no da `0.3` y un reporte de
gastos que no cuadra por céntimos no sirve.

**Validaciones**

- La fecha no puede ser futura.
- La compra debe tener al menos un renglón.
- La cantidad debe ser mayor que cero y el precio unitario no puede ser negativo.
- Ningún descuento puede superar el monto sobre el que se aplica.
- Una compra en colones no lleva conversión de moneda.
- Si se declaró el total del recibo, la diferencia contra el calculado no puede pasar de **1 colón**.
- Toda categoría, comercio y método de pago referenciado debe existir, estar activo y **pertenecer
  al titular**. Esta última es la validación que impide que alguien toque datos de otra cuenta
  pasando un id ajeno.

---

### Proceso 2 · Ingesta y conciliación de un comprobante de correo *(transaccional)*

Es el proceso que da valor real al sistema: el titular vincula su buzón una vez, y de ahí en
adelante sus gastos aparecen clasificados sin digitar nada.

**Pasos**

1. El servicio de ingesta lee un correo nuevo de una `CuentaCorreo` vinculada.
2. Se crea el `Comprobante` en estado `RECIBIDO` con los datos del mensaje: identificador,
   remitente y fecha de recepción. El cuerpo del correo se mantiene solo en memoria.
3. El parser extrae los cuatro campos: monto, últimos 4 dígitos, comercio y fecha. El comprobante
   pasa a `PARSEADO` con un nivel de confianza y **el contenido del correo se descarta**.
4. Se empareja el `MetodoPago` del titular por los últimos cuatro dígitos.
5. Se resuelve el `Comercio` por el nombre normalizado, y de ahí sale la categoría.
6. Se crea la `Compra` con **una sola línea** por el monto total, marcada como categorizada
   automáticamente y con el impuesto sin desglosar.
7. Se sube el contador de la regla que acertó, si hubo alguna.
8. Se actualiza el consumo del `Presupuesto` afectado y se generan las alertas de umbral.
9. El `Comprobante` pasa a `PROCESADO` y queda ligado a la compra.

**Por qué es transaccional**

Este proceso escribe en **cinco tablas**: `comprobante`, `compra`, `linea_compra`,
`regla_categorizacion` y `presupuesto`. Las cinco escrituras tienen que ocurrir **todas o
ninguna**.

Si el paso 8 falla a mitad de camino, quedaría un comprobante marcado como procesado y una compra
creada que nunca impactó el presupuesto: el titular vería el gasto en su lista pero no en su
avance mensual, y no habría forma de detectar la inconsistencia salvo cuadrando a mano compra por
compra. Peor todavía, como el comprobante ya quedó `PROCESADO`, un reintento no lo volvería a
tomar. Por eso los nueve pasos van dentro de una sola transacción, que se implementará cuando el
curso llegue al tema de transacciones.

**Reglas**

- El proceso es **idempotente**: el identificador del mensaje es único. Si el buzón reentrega el
  mismo correo, la ingesta lo rechaza en lugar de duplicar el gasto.
- Por debajo de **0.75 de confianza**, el comprobante no se convierte en compra solo: queda en
  revisión manual. Preferimos molestar al titular antes que meterle un gasto inventado.
- Si los últimos cuatro dígitos no casan con ningún método de pago del titular, la compra se crea
  igual pero marcada para revisión: puede ser una tarjeta que todavía no registró.
- Si el comercio no existe en el catálogo, se crea sin categoría sugerida y la compra queda
  pendiente de clasificar. **La primera vez que el titular la clasifique, esa categoría se guarda
  como sugerida del comercio** y las siguientes compras ahí entran solas.
- Un comprobante que falla tres veces pasa a `FALLIDO` y se le notifica al titular.
- La ingesta solo puede crear compras, nunca modificar ni borrar las que ya existen.
- Un comprobante en moneda extranjera sin tipo de cambio para su fecha queda pendiente hasta que
  la tasa exista. No se inventa una tasa aproximada.

**Cálculos**

- **Confianza del parseo**: proporción de los cuatro campos obligatorios que el parser logró
  extraer, ponderada por qué tan específico era el patrón del remitente que coincidió.
- **Total en moneda base**: `total × tasa_de_la_fecha`, con la tasa de la fecha del comprobante.
- **Consumo de presupuesto**: `monto_consumido += total de la compra en moneda base`.
- **Alerta de umbral**: se dispara cuando `monto_consumido / monto_limite × 100` cruza el umbral
  del presupuesto (80 % por defecto) habiendo estado por debajo antes de esta compra.

**Validaciones**

- El comprobante debe traer identificador de mensaje y remitente.
- No se acepta un comprobante sin cuerpo y sin adjuntos.
- El monto extraído debe ser mayor que cero.
- La fecha extraída no puede ser futura ni anterior a la fecha de alta del titular.
- El comercio detectado debe existir en el catálogo o crearse, nunca quedar nulo.
- La `CuentaCorreo` debe estar activa y con token vigente; si caducó, la sincronización se detiene
  y se le pide al titular que vuelva a vincular.

---

### Cómo se decide la categoría (resumen)

La clasificación es **híbrida y aprende de las correcciones**. Es la única forma de que funcione
sabiendo que el comprobante solo trae el nombre del negocio:

1. **Catálogo semilla.** Al crear la cuenta se siembran ~15 categorías estándar.
2. **Categoría por defecto del comercio.** Automercado → Alimentación acierta la gran mayoría de
   las veces, y es la única señal que trae el correo.
3. **El sistema asigna, pero marca.** La compra entra categorizada y en la interfaz se distingue
   hasta que el titular la confirme.
4. **Corregir crea la regla.** Al cambiar un cargo de «Alimentación» a «Mascotas», el sistema
   ofrece aplicar ese criterio a las próximas compras del mismo comercio.

Automático puro frustra cuando se equivoca; manual puro se abandona a las tres semanas. El ciclo
de corrección es lo que hace que el sistema mejore con el uso sin pedirle a nadie que configure
reglas a mano.

---

## 5 · Alcance

### Dentro del alcance

- **Registro de cuentas**: cualquier persona crea la suya, con sus datos aislados de las demás.
- **Vinculación de uno o varios buzones de correo** por cuenta, con renovación de tokens.
- Registro manual de compras con desglose por renglón y categoría propia por renglón.
- Catálogo de categorías jerárquico con semilla inicial y colores para los gráficos.
- Catálogo compartido de comercios, con categoría sugerida, y métodos de pago por titular.
- Presupuestos mensuales por categoría, con umbral de alerta y avance en vivo.
- Clasificación automática híbrida con aprendizaje por corrección.
- Ingesta de comprobantes desde el buzón, con emparejamiento por últimos cuatro dígitos y
  conciliación transaccional.
- Manejo multimoneda con tipo de cambio histórico y trazabilidad de la tasa aplicada.
- Reportes y gráficos: gasto por categoría, evolución mensual, comparación contra presupuesto,
  gasto por comercio y por método de pago.
- Autenticación y roles (titular, administrador).
- Frontend React con actualización en vivo del avance de presupuesto.
- Exportación de reportes a CSV.

### Fuera del alcance

- **Pagos reales**: el sistema no cobra, no transfiere ni ejecuta ninguna operación financiera.
- **Conexión directa con bancos** (Open Banking o *scraping* de banca en línea). La entrada
  automática es únicamente por correo.
- **Presupuestos compartidos entre varias personas**. Cada cuenta es individual; no hay entidad
  Hogar ni gasto familiar consolidado.
- **Facturación electrónica ante Hacienda**: no se emiten ni validan comprobantes ante el
  Ministerio. Del XML solo se leen los datos de la compra.
- **Archivo de comprobantes.** El sistema no es un repositorio de recibos: lee los correos,
  extrae los datos y los descarta. Quien quiera conservar sus comprobantes los tiene en su
  propio buzón.
- **Aplicación móvil nativa.** El frontend será responsive, pero no habrá app de tienda.
- **Consejo financiero automatizado**: no se recomienda dónde invertir ni se predice gasto futuro.
- **OCR de tiquetes de papel fotografiados.** Solo comprobantes digitales.
- **Contabilidad formal**: no hay partida doble, ni estados financieros, ni cierre contable.
- **Multi-empresa**: el sistema es para personas, no para llevar los gastos de un negocio.

Definir estos límites desde el Laboratorio 1 nos permite enfocar el resto del curso en un dominio
que sí podemos terminar bien.

---

## 6 · Qué se entrega en el Laboratorio 1

Este documento describe el dominio **completo**: las once entidades y los dos procesos de negocio
que se construirán a lo largo del curso.

El código entregado en este laboratorio es deliberadamente el esqueleto mínimo. Implementa **dos**
de esas once entidades —`Categoria`, que es el eje del sistema, y `Usuario`, que es su dueña— para
demostrar la arquitectura por capas funcionando de punta a punta sin adelantar trabajo de los
laboratorios siguientes. Es una decisión de alcance, no una omisión: el dominio que se evalúa en
esta entrega es el de este documento, y el esqueleto se evalúa por su separación de
responsabilidades.

**Entregado en el Laboratorio 1:** la arquitectura por capas, las entidades `Usuario` y
`Categoria` con sus reglas de negocio, y la integración continua.

**Pendiente para los seis laboratorios restantes.** Todavía no conocemos el contenido de cada uno,
así que listamos el trabajo sin asignarle número:

- PostgreSQL con migraciones y las nueve entidades restantes del dominio.
- Frontend React con el avance de presupuesto en vivo.
- El Proceso 2 completo, con su transacción.
- Autenticación, roles, vinculación del buzón e ingesta automática de comprobantes.
