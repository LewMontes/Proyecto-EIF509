# Gastonomo · Control de gastos personales por categorías

[![CI](https://github.com/LewMontes/Proyecto-EIF509-Personal/actions/workflows/ci.yml/badge.svg)](https://github.com/LewMontes/Proyecto-EIF509-Personal/actions/workflows/ci.yml)

Sistema web multiusuario donde cualquier persona crea su cuenta, vincula el buzón donde le llegan
sus comprobantes de compra, y el sistema clasifica su gasto por categoría mostrándole en vivo el
avance contra su presupuesto mensual.

**EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026**
Universidad Nacional · Escuela de Informática y Computación

| |                                                         |
|---|---------------------------------------------------------|
| **Integrantes** | Jose Alexis Solís Carvajal · 1-1623-0238          |
|  |    Luis Antonio Montes de Oca Ruiz · 1-1800-0270     |
| **Entrega actual** | Laboratorio 3 — Persistencia con ORM y repositorios |

---

## Stack

**Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL · MongoDB · React**

> El curso recomienda Java 21 + Spring Boot 3. Este equipo solicitó y obtuvo autorización del
> profesor para usar un stack alternativo equivalente. La justificación técnica completa —con las
> alternativas descartadas y lo que la decisión nos cuesta— está en
> [ADR-001](docs/adr/ADR-001-eleccion-del-stack.md).

---

## Qué incluye este laboratorio

El **Laboratorio 3** entrega **la capa de persistencia**: cómo la aplicación habla con el esquema
que entregó el Laboratorio 2, mediante ORM y el patrón Repository.

| Entregable | Dónde está |
|---|---|
| Mapeo objeto-relacional: 14 entidades, 20 llaves foráneas, **40 relaciones** con carga perezosa razonada | [`src/app/data/models/`](src/app/data/models/) · [Persistencia §2](docs/persistencia.md#2--el-mapeo-objeto-relacional) |
| Repositorio base genérico (`BaseRepository[TEntidad]`), 14 por entidad, más el del subdominio de MongoDB | [`src/app/data/repositories/`](src/app/data/repositories/) · [Persistencia §3](docs/persistencia.md#3--repositorios-con-generalización) |
| 4 consultas de negocio -2 estáticas y 2 dinámicas, una de ellas agregada- con el SQL que el ORM genera, documentado | [Persistencia §4](docs/persistencia.md#4--consultas-de-negocio) |
| Problema N+1 en la lista de compras: medido y corregido. **De 201 consultas a 2**, con pruebas que lo fijan | [Persistencia §5](docs/persistencia.md#5--el-problema-n1) · [`tests/test_n_mas_1.py`](tests/test_n_mas_1.py) |
| 10 pruebas de integración contra un PostgreSQL 16 real (Testcontainers), en verde en el CI | [`tests/integracion/`](tests/integracion/) · [Persistencia §6](docs/persistencia.md#6--cómo-se-prueba) |
| Documento técnico de la capa | [Persistencia](docs/persistencia.md) |

> **Lo único que queda abierto** -y está declarado, no escondido- es que la validación del mapeo
> corra contra el esquema que migra Flyway y no contra el que crea el propio mapeo. La validación
> en sí ya existe y corre en el CI; el detalle está en
> [Persistencia §7](docs/persistencia.md#7--lo-que-queda-abierto).

El **Laboratorio 2**, que sigue en el repositorio, entregó **la capa de datos completa**, con
persistencia políglota:

| Entregable | Dónde está |
|---|---|
| Esquema PostgreSQL en 3FN con migraciones Flyway `V1`…`V5`, restricciones e índices justificados | [`db/postgres/migrations/`](db/postgres/migrations/) |
| Subdominio en MongoDB: la colección `bitacora_compras`, con la decisión de incrustar justificada | [`db/mongo/init/`](db/mongo/init/) · [ADR-002](docs/adr/ADR-002-subdominio-documental-en-mongodb.md) |
| Datos de ejemplo realistas en las dos bases | [`db/postgres/seeds/`](db/postgres/seeds/) · [`db/mongo/init/02_datos_de_ejemplo.js`](db/mongo/init/02_datos_de_ejemplo.js) |
| Documento técnico del modelo y las decisiones de diseño | [Modelo de datos](docs/modelo-de-datos.md) |

En números: **12 tablas · 17 llaves foráneas · 17 restricciones `UNIQUE` · 42 `CHECK` · 46 índices**
en PostgreSQL, más **1 colección con validador de esquema y 4 índices** en MongoDB.

Las migraciones son documentación versionada del modelo -no se aplican con el `docker compose up
-d` de este repositorio, que hoy levanta el esquema real de la aplicación en ejecución (ver
[Cómo levantar la aplicación](#cómo-correr-la-aplicación)). Para migrarlas de verdad sobre un
Postgres vacío hace falta correr Flyway aparte, apuntado a `db/postgres/migrations/` y
`db/postgres/seeds/` -ver [ADR-003](docs/adr/ADR-003-flyway-para-las-migraciones.md). Ese esquema y
el que usa la aplicación en ejecución son **dos linajes distintos**, con dos tablas de diferencia
-la comparación está en
[Persistencia §2.3](docs/persistencia.md#23--estado-del-mapeo-frente-al-esquema-del-laboratorio-2).

El **Laboratorio 1**, que sigue en el repositorio, entregó la arquitectura por capas funcionando de
punta a punta con dos entidades (`Usuario` y `Categoria`) sobre SQLite. La aplicación en ejecución
sigue usando su propio esquema (SQLite por defecto, o PostgreSQL -ver
[Conectarla a PostgreSQL](#conectarla-a-postgresql-en-vez-de-sqlite)-, con tablas creadas por
SQLAlchemy, no por Flyway): el esquema de este apartado es la entrega evaluada del Laboratorio 2,
deliberadamente aparte.

El dominio completo está diseñado y documentado en la
[Propuesta de Dominio](docs/propuesta-dominio.md).

> **Nota:** por decisión del equipo se adelantó, fuera del orden de los laboratorios, todo el
> Proceso 2 del dominio -no solo sobre la base actual de la aplicación, sino construido de verdad:
> vinculación de correo, lectura y clasificación de comprobantes reales de BAC, la transacción
> completa de conciliación (`Compra`, `LineaCompra`, `MetodoPago`, `ReglaCategorizacion`) con
> presupuestos que acumulan consumo real, bitácora de trazabilidad escrita en su propia base de
> MongoDB, reportes exportables y el frontend completo. Se hizo para validar contra un banco real
> -no contra datos inventados- que todo el recorrido de punta a punta funciona. Queda descrito en
> [Funcionalidades adelantadas](#funcionalidades-adelantadas-clasificación-presupuestos-y-reportes)
> y en [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb) más abajo,
> y no es parte de lo que exige el Laboratorio 2.

---

## Cómo correr todo con Docker

Necesitás **Docker Desktop** (o Docker Engine + Compose en Linux) y **OpenSSL** (para el
certificado -ver abajo; en Linux/Mac ya lo tenés). Desde la raíz del repositorio:

```bash
./certs/generar.sh localhost      # o la IP/dominio real, si esto va a un servidor
docker compose up -d
```

El certificado es autofirmado -tu navegador va a avisar "conexión no segura" la primera vez, hay
que aceptar el riesgo para seguir. Hace falta porque el frontend sirve HTTPS de verdad, no HTTP: es
un requisito de Azure/Google si vas a vincular Outlook o Gmail (ver la nota completa en
[`frontend/nginx.conf`](frontend/nginx.conf) y en [`certs/generar.sh`](certs/generar.sh)) -sin
vinculación de correo real, HTTP también funciona, pero igual hace falta el certificado porque
nginx no arranca sin uno.

`docker compose up -d` levanta los cuatro servicios: PostgreSQL, MongoDB, el backend (FastAPI,
imagen armada desde [`Dockerfile`](Dockerfile)) y el frontend (build de producción de Vite servido
por nginx, imagen armada desde [`frontend/Dockerfile`](frontend/Dockerfile); nginx también hace de
proxy hacia el backend bajo el mismo origen, para que el navegador no bloquee esas llamadas como
contenido mixto). No hay que configurar nada más para probarlo local: las credenciales y puertos
traen valores por defecto -para cambiarlos, copiá `.env.ejemplo` a `.env` (ver `BACKEND_PORT`/
`FRONTEND_HTTP_PORT`/`FRONTEND_HTTPS_PORT` ahí, sobre todo si esto corre en un servidor real y no
en tu máquina).

Comprobá que todo quedó arriba:

```bash
docker compose ps
```

Los cuatro contenedores deben decir `Up (healthy)`. La app queda en `https://localhost` (o el
dominio/IP que hayas usado al generar el certificado); el backend solo, en
`http://localhost:8000/docs`.

Si solo querés la capa de datos -por ejemplo, para correr el backend y el frontend directo en tu
máquina en modo desarrollo, con recarga en caliente, en vez de sus imágenes ya compiladas- pedí
nada más esos dos servicios:

```bash
docker compose up -d postgres mongo
```

Mirá los datos de PostgreSQL:

```bash
docker compose exec postgres psql -U gastonomo -d gastonomo -c "\dt"
```

Y los de MongoDB:

```bash
docker compose exec mongo mongosh --quiet -u gastonomo -p gastonomo_local --authenticationDatabase admin gastonomo_app --eval "db.bitacora_compras.find().limit(1)"
```

Para reconstruir las imágenes después de cambiar código (`docker compose up -d` solo no lo hace si
la imagen ya existe):

```bash
docker compose up -d --build
```

Para borrar todo y empezar de cero (pierde los datos de los volúmenes):

```bash
docker compose down -v
```

---

## Funcionalidades adelantadas: clasificación, presupuestos y reportes

Todo esto corre contra correo real de BAC Credomatic -no contra datos de ejemplo-, sobre SQLite o
sobre PostgreSQL (ver [Conectarla a PostgreSQL](#conectarla-a-postgresql-en-vez-de-sqlite)), y es
la parte del sistema que va más allá de lo que exige el Laboratorio 2:

| Funcionalidad | Qué hace | Dónde está |
|---|---|---|
| Resumen financiero | Combina los comprobantes reales de BAC de **todos** los buzones vinculados y los suma por mes y moneda, sin mezclar monedas; se puede navegar a meses anteriores, y cada movimiento muestra de qué buzón salió | [`resumen_service.py`](src/app/business/services/resumen_service.py) |
| Comercios y categorías | Normaliza el nombre del comercio, sugiere su categoría según lo que ese usuario ya clasificó antes (por usuario, no global) y deja confirmar o corregir | [`comercio_service.py`](src/app/business/services/comercio_service.py) |
| Presupuestos | Límite mensual por categoría; `monto_consumido` se acumula de verdad, transacción a transacción, cada vez que una `Compra` real concilia contra esa categoría y ese período (`EN_RANGO` / `CERCA_DEL_LIMITE` / `EXCEDIDO`) -ver [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb) | [`presupuesto_service.py`](src/app/business/services/presupuesto_service.py) |
| Reportes exportables | Movimientos en CSV y Excel, resumen del mes más reciente en PDF | [`reportes.py`](src/app/presentation/routers/reportes.py) |
| Conversión de moneda | Equivalente en colones de un movimiento en dólares, vía el Banco Central. Por defecto es solo referencia; con el selector de moneda del Resumen, todo se convierte a una sola moneda para dar un balance único, diciendo con qué tasa | [`tipo_cambio_service.py`](src/app/business/services/tipo_cambio_service.py) |
| Frontend completo | Ocho pantallas con datos reales o marcadas explícitamente como ejemplo | ver [Correr el frontend](#correr-el-frontend) |

Dos decisiones de dominio que valen la pena explicar:

- **La categoría sugerida de un comercio es por usuario, no global.** Aunque el catálogo de
  comercios (`Comercio`) se comparte entre todos, lo que cada quien clasifica como "Alimentación"
  o "Transporte" es suyo -dos personas pueden categorizar el mismo supermercado distinto. Por eso
  existe `ComercioCategoriaSugerida` como tabla intermedia por `(usuario, comercio)`, en vez de un
  campo `categoria_sugerida` directo en `Comercio`.
- **Un presupuesto acumula su consumo de verdad, no lo recalcula.** `monto_consumido` es una
  columna real que `ConciliacionService` va sumando conforme cada `Compra` se concilia -no un
  número que se recomponía en cada consulta a partir de `Comprobante`. Ver la sección siguiente.

### Caché de comprobantes y sincronización incremental

Hasta hace poco, cada una de estas pantallas releía y reparseaba la bandeja completa del proveedor
en cada petición: con ~110 mensajes, eso son ~110 peticiones HTTP a Microsoft por cada carga de
pantalla, siempre -tuviera o no correo nuevo. Ahora el resultado de parsear cada mensaje se guarda
una sola vez en `Comprobante` ([`comprobante.py`](src/app/data/models/comprobante.py)), con
`mensaje_id` como clave de deduplicación: sincronizar una bandeja ya al día no vuelve a pedirle el
cuerpo a ningún mensaje, solo lista metadatos para ver si hay algo nuevo. `resumen_financiero`
-de donde salen comercios, presupuestos y los tres reportes- sincroniza sola antes de leer, así
que ninguna pantalla necesitó cambiar para beneficiarse. El endpoint
`POST /cuentas-correo/{id}/sincronizar` existe aparte para forzar el pull y confirmar cuánto trajo
de nuevo.

En números, contra un buzón real de ~113 comprobantes: primera carga (bandeja vacía) ~24s, carga
siguiente (bandeja al día) menos de 1s.

### Conversión de moneda (Banco Central de Costa Rica)

Por defecto el Resumen no mezcla monedas en sus totales -es una regla del dominio, no un detalle-
pero un mes con gasto en colones **y** en dólares (un peaje y un viaje de Uber, por ejemplo)
muestra aparte cuánto valdrían esos dólares en colones, solo de referencia.

El selector de **moneda** del Resumen cambia eso a propósito: eligiendo "Todo en colones" o "Todo
en dólares", cada movimiento se convierte a esa moneda antes de sumar y el panel entero pasa a dar
un balance único. No es lo mismo que mezclar a ciegas: hay una tasa real detrás, la pantalla dice
cuál y de qué día, y cada movimiento convertido sigue mostrando el monto que el banco cobró de
verdad. Dos advertencias que la propia pantalla hace explícitas:

- **Cada comprobante se convierte con el tipo de cambio de venta que regía cuando se
  sincronizó**, no con el de hoy -`Comprobante.tipo_cambio_venta`/`tipo_cambio_fecha` lo guardan al
  sincronizar, junto con el gasto. Como una bandeja normalmente se sincroniza el mismo día o al
  siguiente de la compra, en la práctica es la tasa de la compra. Los comprobantes que ya estaban
  guardados antes de que existiera esta columna no tienen tasa propia y caen a la de hoy; la
  pantalla dice cuántos de los que se están mostrando están en ese caso.
- Se convierte con el tipo de cambio de **venta** en las dos direcciones, para que convertir de ida
  y vuelta dé el mismo número. Una moneda que no sea CRC ni USD se deja sin tocar.
- Si el tipo de cambio no está disponible al sincronizar (sin credenciales, o si el BCCR y
  Hacienda fallan los dos), el comprobante se guarda igual, sin tasa -leer el correo nunca depende
  de que un servicio de moneda responda.

La fuente es el
[Servicio Web de Indicadores Económicos](https://gee.bccr.fi.cr/Indicadores/Suscripciones/WS/wsindicadoreseconomicos.asmx)
del Banco Central -el tipo de cambio de referencia oficial del país, gratis y sin necesidad de
tarjeta ni pago. A diferencia de Outlook y Gmail no es OAuth2: hace falta suscribirse una vez,
igual de sencillo pero distinto:

1. Llenar el formulario de <https://gee.bccr.fi.cr/Indicadores/Suscripciones/UI/Suscripcion>:
   nombre, actividad (hay una opción **Estudiantes**), correo, confirmación del correo, idioma y
   la casilla de autorización.
2. Confirmar la suscripción desde el enlace que llega a ese correo.
3. Copiar el token que el BCCR genera al `.env`:

   ```bash
   GASTONOMO_BCCR_CORREO=tu-correo@ejemplo.cr
   GASTONOMO_BCCR_TOKEN=<el token que te dio el BCCR>
   ```

   Si se pierde, se recupera en
   <https://gee.bccr.fi.cr/Indicadores/Suscripciones/UI/RecuperarToken> con el mismo correo.

**Sin suscribirse también funciona.** Si faltan esas variables, o si el BCCR no responde, el
sistema cae a la [API de indicadores del Ministerio de
Hacienda](https://api.hacienda.go.cr/indicadores/tc), que republica ese mismo tipo de cambio de
referencia del BCCR en JSON, sin token ni suscripción. El respaldo solo cubre el día de hoy -ese
endpoint no acepta fechas históricas-, así que para convertir a una fecha pasada sí hace falta la
suscripción al BCCR.

> **Por qué existe el respaldo:** al escribirse esto, todo el subsistema
> `gee.bccr.fi.cr/Indicadores/` llevaba días devolviendo `HTTP 503` — incluida la página donde uno
> se suscribe, así que ni siquiera se podía obtener el token. Sin el respaldo, la conversión de
> moneda quedaba inservible por una caída ajena.

Si las dos fuentes fallan, el aviso de "también tuvo movimientos en $X" se sigue mostrando,
simplemente sin el equivalente en colones al lado: la conversión es un extra, nunca un requisito
para ver el resto del panel.

> **Nota de implementación:** los nombres de parámetro son `Indicador`, `FechaInicio`,
> `FechaFinal`, `Nombre`, `SubNiveles`, `CorreoElectronico` y `Token`, tomados de la página de
> ayuda que el propio ASMX genera para `ObtenerIndicadoresEconomicosXML` (la que documenta la
> invocación por HTTP GET). **No** confundirlos con `tcIndicador`, `tcCorreo`, `tcToken` y
> compañía, que abundan en documentación de terceros: esos son los nombres internos de la
> implementación en VB.NET del BCCR, no los que acepta el lado HTTP. Los siete son obligatorios y
> el BCCR responde `Nothing` -no un error- si falta alguno, así que un nombre mal escrito se
> manifiesta como "no hay tipo de cambio" en vez de como un fallo claro;
> [`test_tipo_cambio_service.py`](tests/test_tipo_cambio_service.py) los fija por eso.
>
> Invocado por GET, el método devuelve el XML de los indicadores **escapado dentro** de un
> elemento `<string xmlns="http://ws.sdde.bccr.fi.cr">`, no como documento propio.

### Conciliación real y bitácora en MongoDB

El dominio completo del Laboratorio 2 -`Compra`, `LineaCompra`, `MetodoPago`,
`ReglaCategorizacion`, `TipoCambio` histórico, `CategoriaEstandar`- corre también dentro de la
aplicación en vivo, no solo en el esquema académico que migra Flyway (ver
[Qué incluye este laboratorio](#qué-incluye-este-laboratorio)). `Comprobante` conserva todos sus
campos actuales tal cual -nada de lo ya construido cambió- y solo ganó una columna nueva,
`compra_id`: la `Compra` real la crea, además, `ConciliacionService`
([`conciliacion_service.py`](src/app/business/services/conciliacion_service.py)), que corre justo
después de guardar cada `Comprobante` con confianza suficiente (`>= 0.75`).

En una sola transacción, `ConciliacionService`:

1. Empareja un `MetodoPago` del titular por sus últimos 4 dígitos -sin match, la compra queda
   marcada `requiere_revision`; nunca se inventa un método de pago. Por eso existe la pantalla
   **Métodos de pago** en el frontend: sin ningún método registrado, la conciliación automática no
   tiene con qué emparejar.
2. Resuelve el `Comercio` (reusa `ComercioService`, sin tocarlo).
3. Categoriza: evalúa las `ReglaCategorizacion` activas del titular por prioridad ascendente contra
   el nombre del comercio: la primera que coincide gana. Sin ninguna regla, cae a
   `ComercioCategoriaSugerida` -el mecanismo que ya existía. Corregir la categoría de un comercio
   después de que ya conciliaron compras suyas sin categoría las corrige retroactivamente.
4. Crea `Compra` + `LineaCompra` (una sola línea; el desglose manual en varias queda para cuando
   haya UI para partir un cargo).
5. Si la moneda no es la base, guarda la tasa usada como fila histórica en `TipoCambio`.
6. Acumula `Presupuesto.monto_consumido` de la categoría y el período afectados, y calcula si cruza
   el umbral de alerta.
7. Enlaza el `Comprobante` a su `Compra` (`compra_id`).

Cada paso también escribe un evento en la **bitácora de trazabilidad**, en MongoDB -el mismo
vocabulario de 13 tipos que ya definía el seed académico
([`db/mongo/init/`](db/mongo/init/), ver [ADR-002](docs/adr/ADR-002-subdominio-documental-en-mongodb.md)),
pero ahora escrito de verdad por la aplicación en vivo, en su propia base **`gastonomo_app`** -a
propósito distinta de `gastonomo`, la que siembra el Laboratorio 2 con compras de ejemplo
numeradas 1-11: compartir la misma colección mezclaría esos ids de ejemplo con el `compra_id`
autoincremental real. Cualquier fallo de Mongo se registra en el log y nunca revierte la
transacción de Postgres -la bitácora explica, no decide, así que un Mongo caído no debería impedir
guardar un gasto real. `GET /api/compras/{id}/bitacora` la expone; en el frontend, cada movimiento
del Resumen que sí concilió una compra tiene un botón que abre esa línea de tiempo completa -de
qué correo nació, cómo se emparejó el método de pago, qué regla lo categorizó, si impactó un
presupuesto- el diferenciador declarado del dominio.

---

## Cómo correr la aplicación

Necesitás **Python 3.12 o superior** (nosotros usamos 3.14). **No hace falta Docker para esta
parte**: por defecto la aplicación usa SQLite local y crea el archivo sola al arrancar -así arranca
también en integración continua, que no levanta Docker.

### Conectarla a PostgreSQL en vez de SQLite

Con `docker compose up -d postgres mongo` corriendo (ver [Cómo correr todo con
Docker](#cómo-correr-todo-con-docker)), esta misma aplicación -corriendo directo en tu máquina, no
en su imagen- puede usar esa base en lugar del archivo local. Es la propia
`Base.metadata.create_all()` la que crea las tablas al arrancar.

En el `.env` (copiado de `.env.ejemplo`):

```bash
GASTONOMO_URL_BASE_DATOS=postgresql+psycopg://gastonomo:gastonomo_local@localhost:5432/gastonomo
```

Sin esa variable, sigue usando SQLite exactamente como antes.

> **Si ya tenías una base de PostgreSQL corriendo de antes:** `create_all()` crea las tablas que
> faltan, pero no altera las que ya existen. Cuando una columna nueva se agrega a un modelo (como
> `tipo_cambio_venta`/`tipo_cambio_fecha` en `comprobante`), una base nueva la recibe sola; una que
> ya venía corriendo necesita el script correspondiente de
> [`db/postgres/esquema-aplicacion/`](db/postgres/esquema-aplicacion/):
>
> ```bash
> docker compose exec -T postgres psql -U gastonomo -d gastonomo \
>   < db/postgres/esquema-aplicacion/001_tipo_cambio_en_comprobante.sql
> ```
>
> Son idempotentes -correrlos de más no hace nada- así que ante la duda conviene correr todos los
> de la carpeta, en orden (`003_transferencias_sinpe.sql` agrega la tabla de transferencias SINPE
> y la bandera `leer_transferencias_sinpe` de `usuario`; el más nuevo, `004_...`, le suma la
> columna `confirmado` a esa tabla).

### 1. Clonar y crear el entorno virtual

```bash
git clone https://github.com/LewMontes/Proyecto-EIF509-Personal.git
```

```bash
python -m venv .venv
```

Activarlo — en **Windows (PowerShell)**:

```bash
.venv\Scripts\Activate.ps1
```

En **Mac / Linux**:

```bash
source .venv/bin/activate
```

### 2. Instalar las dependencias

```bash
pip install -e ".[dev]"
```

### 3. Levantar la aplicación

```bash
uvicorn app.main:app --reload --app-dir src
```

### 4. Probarla

Con la app corriendo, en otra terminal:

```bash
curl http://localhost:8000/api/salud
```

Respuesta esperada:

```json
{"estado":"OK - sistema en linea","aplicacion":"Gastonomo","version":"0.1.0"}
```

La documentación interactiva de la API se genera sola. Abrila en el navegador:

- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc

### Endpoints disponibles

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/salud` | Confirma que el sistema está en línea |
| `POST` | `/api/auth/registro` | Crea la cuenta y devuelve una sesión ya iniciada (token + usuario) |
| `POST` | `/api/auth/iniciar-sesion` | Verifica correo y contraseña, devuelve una sesión nueva |
| `GET` | `/api/auth/yo` | Confirma un token guardado y trae los datos del titular dueño |
| `POST` | `/api/auth/contrasena` | Cambia la contraseña, o le pone una por primera vez a una cuenta de solo Google |
| `GET` | `/api/auth/google/iniciar` | URL de Google para "Iniciar sesión con Google" (público) |
| `POST` | `/api/auth/google/callback` | Completa el login con Google -crea la cuenta si es la primera vez |
| `GET` | `/api/auth/google/vincular/iniciar` | URL de Google para vincular login con Google a la cuenta ya logueada |
| `POST` | `/api/auth/google/vincular/callback` | Completa la vinculación (público: el titular viaja cifrado en `estado`) |
| `DELETE` | `/api/auth/google/vincular` | Desvincula Google -rechaza si es el único método de acceso |
| `POST` | `/api/auth/preferencias/sinpe` | Prende o apaga "Leer transferencias SINPE" -apagado por default |
| `POST` | `/api/categorias` | Crea una categoría aplicando las reglas del dominio |
| `GET` | `/api/categorias?usuario_id=1` | Lista las categorías activas de un usuario |
| `GET` | `/api/cuentas-correo/outlook/iniciar?usuario_id=1` | Da la URL para vincular un buzón de Outlook |
| `GET` | `/api/cuentas-correo/gmail/iniciar?usuario_id=1` | Da la URL para vincular un buzón de Gmail |
| `GET` | `/api/cuentas-correo?usuario_id=1` | Lista los buzones vinculados de un usuario |
| `GET` | `/api/cuentas-correo/resumen-financiero?usuario_id=1` | **Combina** todos los buzones activos y suma por mes; cada comprobante viene marcado con el buzón del que salió. Con `&moneda=CRC` (o `USD`) convierte todo a esa moneda y devuelve la tasa usada en `conversion` |
| `GET` | `/api/cuentas-correo/bancos?usuario_id=1` | Busca "banco" en el asunto de todos los buzones activos y agrupa los remitentes por dominio -candidatos, no confirmaciones: solo BAC tiene parser |
| `GET` | `/api/cuentas-correo/transferencias-sinpe?usuario_id=1` | Busca "transferencia" en el asunto; BAC y Banco Nacional con lector exacto, cualquier otro banco con uno genérico (`confirmado: false`). Vacío sin tocar la red si "Leer transferencias SINPE" está apagado |
| `GET` | `/api/cuentas-correo/comercios?usuario_id=1` | Clasifica los comercios de todos los buzones activos |
| `GET` | `/api/cuentas-correo/presupuestos?usuario_id=1&anio=2026&mes=9` | Estado de los presupuestos contra el gasto real de todos los buzones activos |
| `GET` | `/api/cuentas-correo/reportes/movimientos.csv?usuario_id=1` | Exporta a CSV los movimientos de todos los buzones activos (ídem `.xlsx` y `resumen.pdf`) |
| `GET` | `/api/cuentas-correo/{id}/probar?usuario_id=1` | Trae los últimos mensajes, para confirmar que el token sirve |
| `GET` | `/api/cuentas-correo/{id}/comprobante?usuario_id=1&mensaje_id=…` | Lee y parsea el comprobante de un mensaje puntual |
| `GET` | `/api/cuentas-correo/{id}/resumen-financiero?usuario_id=1` | Sincroniza lo nuevo y suma por mes los comprobantes ya cacheados |
| `POST` | `/api/cuentas-correo/{id}/sincronizar?usuario_id=1` | Fuerza el pull de correo nuevo, sin pedir además todo el resumen |
| `GET` | `/api/cuentas-correo/{id}/comercios?usuario_id=1` | Resuelve y clasifica los comercios de esos comprobantes |
| `GET` | `/api/cuentas-correo/{id}/presupuestos?usuario_id=1&anio=2026&mes=9` | Estado de los presupuestos del período, contra el gasto real de ese mismo período |
| `GET` | `/api/cuentas-correo/{id}/reportes/movimientos.csv?usuario_id=1` | Exporta los movimientos reconocidos a CSV |
| `GET` | `/api/cuentas-correo/{id}/reportes/movimientos.xlsx?usuario_id=1` | Exporta los movimientos reconocidos a Excel |
| `GET` | `/api/cuentas-correo/{id}/reportes/resumen.pdf?usuario_id=1` | Exporta un reporte del mes más reciente en PDF |
| `DELETE` | `/api/cuentas-correo/{id}?usuario_id=1` | Desvincula un buzón |
| `POST` | `/api/comercios/{id}/categoria` | Asigna o corrige la categoría sugerida de un comercio, para ese usuario |
| `POST` | `/api/presupuestos` | Crea o corrige el presupuesto de una categoría y período |
| `GET` | `/api/presupuestos?usuario_id=1&anio=2026&mes=9` | Lista los presupuestos guardados de un período |
| `DELETE` | `/api/presupuestos/{id}?usuario_id=1` | Elimina un presupuesto |
| `GET` | `/api/tipo-cambio?fecha=2026-09-02` | Tipo de cambio de referencia del colón contra el dólar (BCCR) |
| `POST` | `/api/metodos-pago` | Registra un método de pago (alias, tipo, últimos 4 -solo débito/crédito-, entidad, día de corte -solo crédito-) |
| `GET` | `/api/metodos-pago?usuario_id=1` | Lista los métodos de pago del titular |
| `DELETE` | `/api/metodos-pago/{id}?usuario_id=1` | Desactiva un método de pago (no lo borra: una `Compra` ya conciliada sigue apuntándolo) |
| `GET` | `/api/compras?usuario_id=1` | Lista las compras reales del titular, más recientes primero. Con `&requiere_revision=true` trae solo las que quedaron sin método de pago o sin categoría al conciliar |
| `GET` | `/api/compras/gasto-por-categoria?usuario_id=1&anio=2026&mes=9` | En qué se le fue el mes al titular, agrupado y sumado por la base. Acepta `&categoria_id=` (repetible), `&metodo_pago_id=` e `&incluir_sin_categoria=false` -ver [Persistencia §4.4](docs/persistencia.md#44--dinámica-y-agregada--gasto-por-categoría-del-mes) |
| `GET` | `/api/compras/{id}?usuario_id=1` | Detalle de una compra real, con el nombre de su comercio/método/categoría ya resueltos |
| `POST` | `/api/compras/{id}/resolver?usuario_id=1` | Corrige a mano el método de pago y/o la categoría de una compra -pensado para resolver una que quedó `requiere_revision` |
| `GET` | `/api/compras/{id}/bitacora?usuario_id=1` | La trazabilidad completa de una `Compra` real: de qué correo nació, cómo se emparejó el método de pago, qué regla la categorizó, si impactó un presupuesto -ver [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb) más abajo |
| `POST` | `/api/reglas-categorizacion` | Crea una regla de categorización (patrón sobre el nombre del comercio → categoría, con prioridad) |
| `GET` | `/api/reglas-categorizacion?usuario_id=1` | Lista las reglas de categorización del titular, en orden de prioridad |
| `DELETE` | `/api/reglas-categorizacion/{id}?usuario_id=1` | Desactiva una regla (conserva `veces_aplicada` como historial) |

`/api/salud` y los tres de `/api/auth` no necesitan sesión. **Todo lo demás sí**: hace falta el
encabezado `Authorization: Bearer <token>` de una sesión iniciada como el mismo `usuario_id` que se
le pide -ver [Registro y varios usuarios](#registro-y-varios-usuarios) más arriba. Todo lo que lee
correo bajo `/api/cuentas-correo/…` además necesita al menos un buzón ya vinculado con credenciales
reales de Microsoft/Google — ver la sección **Vinculación de correo** más abajo. Las rutas con
`{id}` operan sobre **un** buzón puntual; las que no lo llevan combinan todos los buzones activos
del titular, que es lo que usa el frontend. `/api/tipo-cambio` necesita la suscripción del Banco
Central — ver [Conversión de moneda](#conversión-de-moneda-banco-central-de-costa-rica) más arriba.

### 5. Correr las pruebas y el linter

```bash
pytest -v
```

```bash
ruff check . && ruff format --check .
```

Son los mismos comandos que ejecuta la integración continua. **352 pruebas** corren contra una
base SQLite **en memoria**, así que no tocan ningún archivo ni necesitan infraestructura.

Aparte están las **10 pruebas de integración**, que levantan un PostgreSQL 16 real en Docker con
Testcontainers y lo apagan al terminar:

```bash
pytest -m integracion
```

Verifican lo que SQLite no puede detectar -`NUMERIC` decimal exacto, `ON DELETE CASCADE`, el largo
de los `VARCHAR`, el `ROLLBACK` real, y que el mapeo calce con el esquema que hay en la base. Si no
tenés Docker corriendo **se saltan solas**, no fallan. Para correr solo las rápidas:

```bash
pytest -m "not integracion"
```

El detalle de qué prueba cada una está en [Persistencia §6](docs/persistencia.md#6--cómo-se-prueba).

El frontend tiene su propia suite, con Vitest + Testing Library (`cd frontend`):

```bash
npm run test
```

```bash
npx tsc -b && npm run lint
```

50 pruebas: funciones puras de `lib/formato.ts`, `api.ts` con `fetch` mockeado (URL, encabezados,
traducción de errores), los hooks `useSesion`/`useCuentaActiva`, y componentes de pantalla completos
(`Bancos.tsx` en sus tres estados, el CRUD de `MetodosPago.tsx` y `ReglasCategorizacion.tsx`, el
filtro y la corrección inline de `Compras.tsx`) contra un doble de `api`, sin tocar la red. También
corre en CI, junto a `pytest`.

---

## Cómo está organizado

Arquitectura en tres capas más configuración. La regla de oro:
**presentación → negocio → datos, nunca al revés.**

```
src/app/
├── presentation/   → Habla HTTP. Recibe JSON, llama al servicio, devuelve JSON.
│   ├── routers/        salud.py · categorias.py · cuentas_correo.py · comercios.py ·
│   │                   presupuestos.py · reportes.py · metodos_pago.py · compras.py ·
│   │                   reglas_categorizacion.py
│   ├── schemas.py      DTOs de entrada y salida
│   └── dependencies.py arma los servicios con sus repositorios
│
├── business/       → Reglas del negocio. No sabe que existe HTTP.
│   ├── services/        categoria_service.py · cuenta_correo_service.py ·
│   │                    comercio_service.py · presupuesto_service.py · resumen_service.py ·
│   │                    metodo_pago_service.py · conciliacion_service.py · compra_service.py ·
│   │                    regla_categorizacion_service.py · bitacora_service.py (escribe en MongoDB)
│   │   └── correo/      proveedor.py · outlook.py · gmail.py (hablan con Microsoft/Google)
│   ├── parsers/          comprobante_bac.py (lee notificaciones de BAC con regex)
│   ├── seguridad/        cifrado.py (cifra los tokens antes de guardarlos)
│   └── errors.py        violaciones de reglas del dominio
│
├── data/           → Entidades y consultas. No contiene reglas de negocio.
│   ├── models/          usuario.py · categoria.py · cuenta_correo.py · comercio.py ·
│   │                    comercio_categoria_sugerida.py · presupuesto.py · comprobante.py ·
│   │                    compra.py · linea_compra.py · metodo_pago.py · regla_categorizacion.py ·
│   │                    tipo_cambio.py · categoria_estandar.py · transferencia_sinpe.py ·
│   │                    base.py · enums.py · tipos.py
│   └── repositories/    el único lugar del sistema que consulta datos: base_repository.py
│                        (genérico), 14 por entidad, y bitacora_repository.py (MongoDB)
│
├── config/         → Lo que cambia entre máquinas.
│   ├── settings.py      nombre, versión, URL de la base, credenciales OAuth, Mongo
│   ├── database.py      motor, sesión y creación de tablas
│   ├── cliente_http.py  cliente HTTP compartido hacia Microsoft/Google
│   └── cliente_mongo.py cliente Mongo compartido hacia `gastonomo_app` (ver más abajo)
│
└── main.py         → Arma la app, CORS, y traduce errores de negocio a códigos HTTP.
```

El frontend vive aparte, en [`frontend/`](frontend/) — ver [Correr el frontend](#correr-el-frontend).

Tres decisiones sostienen la separación, ya que Python no la impone por sí solo:

1. El servicio recibe una **dataclass propia** (`CrearCategoriaComando`), no un modelo de FastAPI.
2. El repositorio **nunca confirma la transacción**: el `commit` lo hace el servicio, que es el
   único que sabe si la operación de negocio completa terminó bien.
3. Los errores de negocio son **excepciones propias** sin ninguna referencia a HTTP; `main.py` es
   el único archivo que las traduce a códigos de respuesta.

---

## Registro y varios usuarios

Cualquier persona crea su cuenta desde la pantalla de login (correo, contraseña, nombre) y ve
únicamente lo suyo -sus categorías, sus buzones vinculados, sus comprobantes. Antes de esto el
`usuario_id` se elegía a mano en un campo de texto del encabezado -sin ninguna autenticación detrás,
cualquiera podía ver los datos de cualquier otro con solo cambiar el número.

**Cómo funciona el login**, sin tabla de sesiones ni JWT: `POST /api/auth/registro` o
`/api/auth/iniciar-sesion` devuelven un token que es, literalmente, el `usuario_id` cifrado con
[Fernet](https://cryptography.io/en/latest/fernet/) -el mismo mecanismo simétrico que ya cifra los
tokens de Outlook/Gmail y el `state` del handshake de OAuth2 (ver más abajo), reutilizado en vez de
sumar una librería de JWT. El frontend lo guarda en `localStorage` y lo manda como
`Authorization: Bearer <token>` en cada pedido
([`api.ts`](frontend/src/api.ts)); el backend lo descifra, confirma que no venció (30 días de vida)
y ya sabe quién pregunta -no hace falta ninguna tabla de sesiones que limpiar, y "cerrar sesión" es,
del todo, que el cliente se olvide del token.

**El resto de la API sigue recibiendo `usuario_id` explícito** -no cambió el contrato- pero ahora
cada endpoint exige que la sesión activa sea la de ese mismo titular
([`verificar_titular`/`verificar_mismo_usuario`](src/app/presentation/dependencies.py)): pedir los
datos de otro id da `403`, no los datos de otro id. Las contraseñas se guardan con
[bcrypt](https://pypi.org/project/bcrypt/), nunca en claro.

> **Cuenta de prueba:** una base recién creada siembra un usuario de prueba
> ([`sembrar_usuario_de_demostracion`](src/app/config/database.py)) para poder probar la API sin
> pasar por el registro, con el correo y la contraseña de `GASTONOMO_DEMO_CORREO`/
> `GASTONOMO_DEMO_CONTRASENA` en `.env` -por defecto, si no están seteadas,
> `demo@gastonomo.cr` / `demo1234`. Viven en `.env` (gitignorado) y no como constante en el código
> a propósito: ese archivo sí se sube al repositorio, y una contraseña real -aunque sea la de una
> cuenta de prueba- no debería quedar en texto plano ahí. En una base que ya tenía usuarios de
> antes de que este login existiera -la de este mismo repositorio en desarrollo, por ejemplo- esa
> contraseña se puso a mano una sola vez con `hashear_contrasena(...)`; no hay una migración de
> datos que la reponga sola.

### Iniciar sesión con Google

El botón "Continuar con Google" de la pantalla de login crea la cuenta si es la primera vez, o
entra a la que ya existía -el mismo botón para las dos cosas, la decisión la toma el backend según
si ya conoce el `google_id` (el identificador estable de esa cuenta de Google) que Google le
confirma. Reusa el cliente OAuth2 que ya existe para vincular Gmail (mismo `Client ID`/`Secret` en
Google Cloud), pero con un alcance mucho más chico -`openid email profile`, nunca
`gmail.readonly`- y su propio `redirect_uri` registrado aparte
(`GASTONOMO_GOOGLE_LOGIN_REDIRECT_URI`, ver
[Registrar las apps](#registrar-las-apps-una-sola-vez-por-integrante) más abajo).

Una cuenta que entra solo por Google no tiene contraseña
(`Usuario.contrasena_hash` queda en `NULL`) hasta que le pongan una desde **Ajustes → Mi cuenta**.
Ahí mismo se vincula o desvincula Google a una cuenta que ya tenía contraseña -desvincularlo se
rechaza si es el único método de acceso que le queda al titular, para no dejar una cuenta sin
ninguna forma de entrar.

**Por qué un correo que coincide no vincula solo:** si ya existe una cuenta local con ese mismo
correo pero sin Google vinculado todavía, iniciar sesión con Google *no* entra ahí -nadie confirmó
que quien tiene esa cuenta de Google ahora mismo sea la misma persona dueña de esa contraseña. El
mensaje que se muestra pide iniciar sesión con la contraseña y vincular Google desde Ajustes, un
paso explícito y ya autenticado.

---

## Vinculación de correo (Outlook y Gmail)

El sistema vincula un buzón de Outlook o de Gmail vía OAuth2 y, una vez vinculado, lee sus
mensajes de BAC Credomatic, los parsea con
[`business/parsers/comprobante_bac.py`](src/app/business/parsers/comprobante_bac.py) y arma con
eso el resumen financiero, la clasificación por comercio, el estado de los presupuestos y los
reportes exportables -ver [Funcionalidades adelantadas](#funcionalidades-adelantadas-clasificación-presupuestos-y-reportes)
más arriba. Es la base del Proceso 2 de ingesta de comprobantes descrito en la
[Propuesta de Dominio](docs/propuesta-dominio.md); lo que falta de ese proceso es la parte
transaccional -conciliar contra un presupuesto guardado en vez de calcularlo al vuelo, y sumar
otros bancos además de BAC.

### Por qué el frontend es dueño del `redirect_uri`

Microsoft y Google devuelven al titular, tras autorizar, a una URL que **nosotros** registramos de
antemano. Esa URL apunta al frontend (`http://localhost:5173/vincular/outlook/callback`), no al
backend: así el navegador nunca aterriza en un JSON crudo. El frontend lee `code` y `state` de la
URL y se los pasa al backend por `fetch` — ahí sí se completa la vinculación. El `state` no
necesita una sesión de servidor: es el `usuario_id` cifrado con la misma clave de los tokens, así
que el backend lo descifra sin tener que recordar nada entre la ida y la vuelta.

### Registrar las apps (una sola vez, por integrante)

**Azure AD / Entra ID (Outlook):**

1. https://portal.azure.com → *Microsoft Entra ID* → *App registrations* → *New registration*.
2. Nombre `Gastonomo`. **Supported account types**: *Personal Microsoft accounts only*.
3. Redirect URI tipo *Web*: `http://localhost:5173/vincular/outlook/callback`.
4. *Certificates & secrets* → *New client secret* → copiar el valor (solo se ve una vez).
5. *API permissions* → *Add a permission* → *Microsoft Graph* → *Delegated* → `Mail.Read`,
   `User.Read`, `offline_access`.

**Google Cloud (Gmail):**

1. https://console.cloud.google.com → crear proyecto → *APIs & Services* → *Library* → habilitar
   **Gmail API**.
2. *OAuth consent screen*: tipo *External*, agregarte como *Test user* (mientras la app esté en
   modo *Testing*, solo los correos que agregues ahí pueden autorizarla — el tuyo, el de quien
   pruebe con vos).
3. En esa misma pantalla, *Data Access* → *Add or Remove Scopes* → agregar
   `https://www.googleapis.com/auth/gmail.readonly` y `.../auth/userinfo.email` (o el genérico
   `email`) — sin este paso Google rechaza el consentimiento aunque el código pida los scopes
   correctos; a diferencia de Azure, acá hay que declararlos en la consola, no solo en el código.
4. *Credentials* → *Create credentials* → *OAuth client ID* → tipo *Web application*.
5. **Dos** Redirect URI en ese mismo cliente -no dos clientes distintos:
   - `http://localhost:5173/vincular/gmail/callback` (vincular un buzón para leerlo)
   - `http://localhost:5173/iniciar-sesion/google/callback` ("Iniciar sesión con Google")

   Comparten Client ID y Secret; lo que cambia es el alcance que cada uno pide (`gmail.readonly`
   contra apenas `openid email profile`) y a qué pantalla del frontend vuelve el titular.

### Configurar el backend

Crear un archivo `.env` en la raíz del proyecto (no se sube: está en `.gitignore`) o exportar las
variables antes de levantar `uvicorn`:

```bash
GASTONOMO_MICROSOFT_CLIENT_ID=<el client id de Azure>
GASTONOMO_MICROSOFT_CLIENT_SECRET=<el secreto de Azure>
GASTONOMO_GOOGLE_CLIENT_ID=<el client id de Google>
GASTONOMO_GOOGLE_CLIENT_SECRET=<el secreto de Google>
GASTONOMO_CLAVE_CIFRADO_TOKENS=<ver el comando de abajo>
```

La clave de cifrado protege los tokens guardados en la base. Sin ella el sistema arranca igual con
una clave temporal, pero avisa por warning y los tokens no sobreviven un reinicio:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Los valores por defecto de `microsoft_redirect_uri`, `google_redirect_uri`,
`google_login_redirect_uri` y CORS ya apuntan al frontend en `http://localhost:5173`; solo hay que
tocarlos si se corre en otro puerto o dominio.

> **Corriendo con Docker (ver [Cómo correr todo con Docker](#cómo-correr-todo-con-docker)):** el
> frontend queda en HTTPS, no en `http://localhost:5173` -Azure y Google exigen que el redirect URI
> empiece con "https" salvo que sea literalmente `http://localhost`. Registrá ahí los tres
> `https://<tu-ip-o-dominio>/...` correspondientes (mismas rutas, mismo puerto que uses si no es el
> 443 por defecto) en vez de los de `localhost:5173` de arriba, y poné esas mismas URLs en
> `GASTONOMO_MICROSOFT_REDIRECT_URI`/`GASTONOMO_GOOGLE_REDIRECT_URI`/
> `GASTONOMO_GOOGLE_LOGIN_REDIRECT_URI`/`GASTONOMO_ORIGENES_PERMITIDOS` del `.env`.

### Correr el frontend

```bash
cd frontend
npm install
npm run dev
```

Abre en `http://localhost:5173`. Por ahora no hay login: se elige un `usuario_id` desde el
encabezado (el Laboratorio 1 siembra el usuario de demostración con id `1`).

Sin credenciales de Microsoft/Google configuradas, el botón de conectar igual redirige al proveedor
real, que rechaza la solicitud con un error legible (`unauthorized_client`) — es la forma de
confirmar que el flujo está bien armado antes de tener las credenciales a mano. Con un buzón real
vinculado, estas pantallas quedan disponibles:

| Pantalla | Con qué datos trabaja |
|---|---|
| **Resumen** | Gasto real del mes, tendencia, top comercios y calendario, extraídos en vivo del buzón vinculado |
| **Categorías** | Categorías reales del usuario; comercios ya clasificados agrupados por categoría, y los pendientes de clasificar |
| **Presupuestos** | Alta y baja de presupuestos reales por categoría y período, con su estado calculado contra el gasto real |
| **Reportes** | Descarga de CSV, Excel y PDF de los movimientos reales |
| **Conectar correo** | Vincular o desvincular Outlook y Gmail |
| **Bancos** | Busca "banco" de verdad en los buzones vinculados y agrupa por dominio del remitente; BAC aparece "Conectado" (tiene parser), el resto queda marcado como candidato sin soporte todavía |
| **SINPE** | Transferencias SINPE recibidas, reales; BAC y Banco Nacional con lector exacto, cualquier otro banco detectado automáticamente con patrones generales y marcado "Sin confirmar". Apagada por default -se prende desde acá o desde Ajustes |
| **Métodos de pago** | CRUD real de los métodos del titular -sin esto, la conciliación automática no tiene con qué emparejar los últimos 4 dígitos de un comprobante. Cada movimiento del Resumen que concilió una compra real tiene un botón que abre su bitácora completa -ver [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb) |
| **Compras** | Las `Compra` reales, de primera clase -antes solo se veían indirectamente. Filtro "Pendientes de revisión" (default) para las que quedaron sin método de pago o sin categoría, con selectores inline para corregirlas sin salir de la lista |
| **Reglas de categorización** | CRUD de `ReglaCategorizacion`: patrón sobre el nombre del comercio → categoría, con prioridad. Se evalúan antes que la categoría sugerida del comercio |
| **Ajustes** *(datos de ejemplo)* | Prototipo de la pantalla, marcado explícitamente como no conectado todavía |

Cada comprobante de BAC se lee y se guarda una sola vez -ver
[Caché de comprobantes](#caché-de-comprobantes-y-sincronización-incremental) más abajo. La primera
carga de un buzón nuevo puede tardar varios segundos; las siguientes, con la bandeja ya al día,
son casi instantáneas.

---

## Camino a publicar en App Store y Play Store

La app está preparada para empaquetarse como app nativa y venderse, pero publicarla de verdad
necesita varios trámites que son tuyos -tu identidad, tu tarjeta, tus cuentas de desarrollador- y
no se pueden automatizar desde acá. Esta sección es el mapa completo: qué ya está hecho, y qué
falta y en qué orden.

### El enfoque: envolver la web, no reescribirla

La app móvil no es un proyecto aparte -es este mismo frontend de React, empaquetado con
[Capacitor](https://capacitorjs.com/) en un shell nativo real para cada tienda. `npm run build`
genera el mismo `dist/` que ya sirve Vite; Capacitor lo copia dentro de un proyecto de Android (y,
en una Mac, de iOS) y lo corre ahí. Cualquier pantalla nueva o corregida en `frontend/src/` llega
a la app móvil con `npm run cap:sync`, sin duplicar una sola línea.

### Lo que ya está hecho

| Qué | Dónde |
|---|---|
| Interfaz responsiva de verdad -el sidebar es un cajón deslizable en pantallas angostas, las grillas colapsan a una columna, nada desborda- verificado en un viewport de 375px | [`Sidebar.tsx`](frontend/src/components/Sidebar.tsx), [`index.css`](frontend/src/index.css) |
| Manifest de PWA, íconos en todos los tamaños que piden iOS/Android/favicon, metatags de instalación | [`manifest.webmanifest`](frontend/public/manifest.webmanifest), [`index.html`](frontend/index.html) |
| Política de privacidad y Términos de uso reales, accesibles sin sesión -exigidos por la verificación de OAuth de Google y por la revisión de las dos tiendas | `/privacidad` y `/terminos` ([`pages/legal/`](frontend/src/pages/legal/)) |
| Proyecto de Android generado y sincronizado, con sus propios íconos adaptativos y splash screen | [`capacitor.config.ts`](frontend/capacitor.config.ts), `frontend/android/` |

### Lo que falta, en orden

**1. Cuentas de desarrollador** *(tuyas, con tu identidad y tu tarjeta -no las puedo crear)*

- [Apple Developer Program](https://developer.apple.com/programs/): USD 99/año. Para publicar en
  iOS hace falta además una Mac con Xcode -no se puede compilar ni firmar un `.ipa` desde Windows.
- [Google Play Console](https://play.google.com/console/): USD 25, pago único.

**2. Hosting en producción** *(el backend hoy corre en tu máquina, con SQLite o con el Postgres de
Docker Compose -nada de eso sirve para una app pública)*

- Elegir dónde vive el backend + Postgres (Railway, Render y Fly.io son las opciones más simples
  para un FastAPI chico; cualquiera con HTTPS incluido sirve).
- Un dominio real con HTTPS -Google exige HTTPS para el `redirect_uri` de producción, y Apple/Google
  rechazan una app que hable con un backend sin cifrar.
- Cambiar `VITE_API_URL` (frontend) a esa URL real antes de `npm run build`, y agregar el origen de
  la app nativa (`capacitor://localhost` en iOS, `http://localhost` en Android -así es como
  Capacitor identifica el origen de la webview) a `GASTONOMO_ORIGENES_PERMITIDOS` en el backend.
- Mover `GASTONOMO_CLAVE_CIFRADO_TOKENS` a un secreto real del hosting elegido -hoy puede arrancar
  con una clave efímera de desarrollo si no está seteada, lo cual está bien en local y sería un
  error grave en producción (los tokens cifrados no sobrevivirían un reinicio).

**3. Verificación de OAuth** *(sin esto, cualquiera que no seas vos ve una pantalla de advertencia
de Google/Microsoft al intentar vincular su correo, o directamente no puede)*

- **Google:** la app pide `gmail.readonly`, un scope "sensible". Hace falta enviarla a
  [verificación](https://support.google.com/cloud/answer/13463073) con la política de privacidad ya
  publicada (`/privacidad`, ver arriba), puede pedir un video mostrando el flujo de consentimiento,
  y Google la revisa -típicamente unas pocas semanas. Mientras tanto, la app sigue funcionando en
  modo "Testing" solo para los correos que agregues a mano como usuarios de prueba (ver
  [Registrar las apps](#registrar-las-apps-una-sola-vez-por-integrante) más abajo).
- **Microsoft:** el registro actual es de un solo tenant (`common`, ver
  [Por qué el frontend es dueño del redirect_uri](#por-qué-el-frontend-es-dueño-del-redirect_uri)).
  Para una app pública conviene registrar el `redirect_uri` de producción y revisar el estado de
  verificación del publicador en Azure AD.
- En los dos casos, actualizar el `redirect_uri` registrado para que apunte al dominio de
  producción, no a `localhost`.

**4. Identidad de la app en las tiendas**

- Cambiar `appId` en [`capacitor.config.ts`](frontend/capacitor.config.ts) -hoy es
  `com.gastonomo.app`, un valor de relleno- por el identificador real que registrés en cada
  consola. Cambiarlo después de la primera publicación obliga a subir la app como una ficha nueva,
  no como una actualización, así que conviene decidirlo antes de publicar la primera vez.
- Si cambia el nombre o los colores de marca, regenerar los íconos:
  `npx @capacitor/assets generate` lee `frontend/assets/icon.png` (el ícono maestro de 1024×1024)
  y genera todos los tamaños de nuevo para Android (y para iOS, una vez que exista ese proyecto).

**5. Compilar, firmar y subir**

- **Android:** `npm run cap:android` abre el proyecto en Android Studio (necesita el Android SDK
  instalado -no viene con Capacitor). Generás ahí el `.aab` firmado con tu propia keystore y lo
  subís a Play Console.
- **iOS:** en una Mac, `npx cap add ios` agrega el proyecto (no se pudo generar en este ambiente
  Windows); `npx cap open ios` lo abre en Xcode para firmar con tu cuenta de Apple Developer y
  subir a App Store Connect.
- Cada tienda pide capturas de pantalla reales en tamaños específicos, una descripción, una
  categoría, y un cuestionario de clasificación de contenido y de manejo de datos ("Data safety" en
  Play, "App Privacy" en App Store) -ahí es donde la Política de privacidad de arriba responde
  directamente las preguntas que piden.

### Sobre cobrar por la app

Esta ronda dejó la base lista -hosting multi-usuario, política de privacidad, términos de uso- pero
**sin cobros integrados todavía**, a propósito: activar pagos de verdad significa abrir una cuenta
de Stripe o configurar las suscripciones de RevenueCat/App Store/Play Store con tu identidad fiscal
real, y ninguna de esas cuentas se puede crear por vos. El código para integrarlo, una vez que esas
cuentas existan, es un paso aparte y bien acotado -avisá cuando quieras encararlo.

---

## Documentación

| Documento | Qué contiene |
|---|---|
| [Persistencia](docs/persistencia.md) | **Laboratorio 3.** El mapeo objeto-relacional, los repositorios con generalización, las consultas de negocio con su SQL generado, la evidencia del N+1 y lo que falta por cerrar. |
| [Modelo de datos](docs/modelo-de-datos.md) | **Laboratorio 2.** El esquema relacional, su normalización, sus restricciones e índices justificados, y el subdominio de MongoDB con su justificación completa. |
| [Propuesta de Dominio](docs/propuesta-dominio.md) | El negocio, los actores, las entidades y los 2 procesos con sus reglas, cálculos y validaciones. |
| [Arquitectura](docs/arquitectura.md) | Diagramas de capas, recorrido de una petición, modelo entidad-relación y despliegue previsto. |
| [ADR-001 · Elección del stack](docs/adr/ADR-001-eleccion-del-stack.md) | Por qué Python + FastAPI + PostgreSQL + React, qué descartamos y qué nos cuesta. |
| [ADR-002 · Subdominio documental](docs/adr/ADR-002-subdominio-documental-en-mongodb.md) | Por qué la trazabilidad de la compra va en MongoDB incrustada, qué candidatos descartamos y qué invalidaría la decisión. |
| [ADR-003 · Flyway para las migraciones](docs/adr/ADR-003-flyway-para-las-migraciones.md) | Por qué Flyway en un contenedor en lugar de Alembic, y qué nos cuesta. |

---

## Integración continua

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre en cada push y en cada pull request
sobre `main` y `master`. Instala el proyecto en una máquina limpia, revisa el código con `ruff`,
ejecuta la suite de pruebas, corre las **pruebas de integración contra un PostgreSQL real**
(Testcontainers levanta el contenedor dentro del propio runner) y **levanta el servidor de verdad**
para confirmar que `/api/salud` responde.

El estado se ve en la pestaña **Actions** del repositorio y en la insignia del inicio de este
README.

---

## Estado del proyecto

El curso son siete laboratorios incrementales sobre esta misma base. Todavía no sabemos el
contenido exacto de cada uno, así que lo pendiente queda listado sin asignarle número.

- [x] **Laboratorio 1** *(entregado)* — Arquitectura por capas, `Usuario` y `Categoria`, propuesta de dominio, CI
- [x] **Laboratorio 2** *(entregado)* — Capa de datos completa: PostgreSQL con Flyway, subdominio
      documental en MongoDB, restricciones e índices probados. Ver
      [Qué incluye este laboratorio](#qué-incluye-este-laboratorio).
- [x] **Laboratorio 3** *(entregado)* — Persistencia con ORM y repositorios: las 14 entidades con
      sus 40 relaciones y carga perezosa razonada, repositorio base genérico más 14 específicos y
      el del subdominio de MongoDB, 4 consultas de negocio con su SQL documentado, el N+1 de la
      lista de compras medido y corregido (201 consultas → 2) y 10 pruebas de integración contra
      PostgreSQL real con Testcontainers. Ver [Persistencia](docs/persistencia.md).
- [x] **Vinculación OAuth2 de buzones** *(adelantado, fuera de orden)* — Outlook y Gmail.
      Ver [Vinculación de correo](#vinculación-de-correo-outlook-y-gmail).
- [x] **Parser de comprobantes de BAC** *(adelantado)* — probado contra notificaciones reales,
      confianza 1.0 en los ocho campos. [`comprobante_bac.py`](src/app/business/parsers/comprobante_bac.py)
- [x] **Clasificación por comercio, presupuestos y reportes** *(adelantado)* — contra correo real,
      con estado de presupuesto calculado en vivo y exportación a CSV/Excel/PDF.
      Ver [Funcionalidades adelantadas](#funcionalidades-adelantadas-clasificación-presupuestos-y-reportes).
- [x] **Frontend completo** *(adelantado)* — siete pantallas; cinco con datos reales, dos marcadas
      explícitamente como prototipo. Ver [Correr el frontend](#correr-el-frontend).
- [x] **Caché local y sincronización incremental** *(adelantado)* — los comprobantes ya no se
      releen del proveedor en cada petición. Ver
      [Caché de comprobantes](#caché-de-comprobantes-y-sincronización-incremental).
- [x] **La aplicación puede correr sobre PostgreSQL** *(adelantado)* — `GASTONOMO_URL_BASE_DATOS`
      la conecta al Postgres de `docker compose up -d` en vez de SQLite, con su propio esquema
      (`Base.metadata.create_all()`, no Flyway). Ver
      [Conectarla a PostgreSQL](#conectarla-a-postgresql-en-vez-de-sqlite).
- [x] **Selector de mes en el Resumen** *(adelantado)* — antes solo mostraba el mes más reciente.
- [x] **Conversión de moneda de referencia** *(adelantado)* — equivalente aproximado en colones de
      un movimiento en dólares, vía el Banco Central. Ver
      [Conversión de moneda](#conversión-de-moneda-banco-central-de-costa-rica).
- [x] **Interfaz responsiva y proyecto móvil (Capacitor)** *(adelantado)* — el mismo frontend
      empaquetado para Android/iOS, íconos, manifest de PWA, política de privacidad y términos de
      uso reales. Ver [Camino a publicar en App Store y Play Store](#camino-a-publicar-en-app-store-y-play-store).
- [x] **Transferencias SINPE recibidas, leídas de verdad** *(adelantado)* — parser exacto de BAC y
      del Banco Nacional, cada uno validado contra una notificación real (ver
      `business/parsers/transferencia_sinpe.py`); cualquier otro banco cae a un lector genérico
      (monto, cuenta IBAN, fecha, referencia -los mismos campos que casi cualquier notificación de
      SINPE comparte) y queda marcado `confirmado: false` -la pantalla lo muestra igual, pero para
      revisar, nunca como un dato tan confiable como los de BAC/Banco Nacional. Un mensaje sin
      nada útil que extraer ni siquiera llega a guardarse. Pestaña SINPE nueva, conectada al
      interruptor "Leer transferencias SINPE" de Ajustes -apagado por default, porque sincronizar
      es una petición real por buzón.
- [x] **Conciliación real y bitácora en MongoDB** *(adelantado)* — el dominio completo del
      Laboratorio 2 (`Compra`, `LineaCompra`, `MetodoPago`, `ReglaCategorizacion`) corre también
      dentro de la app en vivo: cada comprobante confiable concilia una `Compra` real en una sola
      transacción, `Presupuesto.monto_consumido` se acumula de verdad en vez de recalcularse, y
      cada paso queda escrito en MongoDB. Ver
      [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb).
- [x] **Pantalla Métodos de pago y panel de bitácora** *(adelantado)* — CRUD de métodos de pago
      (sin el cual la conciliación no tiene con qué emparejar últimos 4 dígitos) y un panel
      deslizable en el Resumen con la línea de tiempo completa de cada compra conciliada.
- [x] **Pruebas automatizadas de frontend** *(adelantado)* — Vitest + Testing Library, 39 pruebas
      contra `lib/formato.ts`, `api.ts`, los hooks de sesión y dos pantallas completas. Ver
      [Correr las pruebas y el linter](#5-correr-las-pruebas-y-el-linter).
- [x] **`ReglaCategorizacion` real y `Compra` de primera clase** *(adelantado)* — una auditoría de
      pantallas encontró que `ReglaCategorizacion` no tenía ningún endpoint que la creara (el motor
      de categorización siempre caía a la sugerencia del comercio) y que `Compra` -el resultado real
      de conciliar un comprobante- solo se podía ver indirectamente, sin que `requiere_revision`
      llegara a ningún lado. Pantallas nuevas **Reglas de categorización** (CRUD) y **Compras**
      (listado filtrable por "pendientes de revisión", con corrección inline del método de pago y
      la categoría). 305 → 336 pruebas de backend, 39 → 50 de frontend.
- [x] **Backend y frontend dockerizados** *(adelantado)* — `docker compose up -d` levanta los
      cuatro servicios de la aplicación en vivo (Postgres, Mongo, backend con
      [`Dockerfile`](Dockerfile), frontend con [`frontend/Dockerfile`](frontend/Dockerfile) de dos
      etapas: build de Vite servido por nginx). Antes solo la capa de datos estaba en Docker; el
      backend y el frontend corrían aparte. De paso, `docker-compose.yml` dejó de convivir con el
      servicio de Flyway del Laboratorio 2 -las migraciones siguen documentadas en
      `db/postgres/migrations/` (ver [ADR-003](docs/adr/ADR-003-flyway-para-las-migraciones.md)),
      pero ya no comparten archivo con la infraestructura de la app en vivo. Ver
      [Cómo correr todo con Docker](#cómo-correr-todo-con-docker).

Pendiente:

- [x] Conectar la aplicación a MongoDB para lo que corresponda al subdominio documental -ver
      [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb)
- [x] Vinculación de Gmail en el frontend, de punta a punta contra una cuenta real de Google
- [ ] Sumar otros bancos además de BAC a las compras -contra una notificación real de cada uno,
      igual que siempre. Para transferencias SINPE ya hay un lector genérico que cubre cualquier
      banco de forma aproximada (ver arriba); un lector exacto validado para otro banco puntual
      sigue pendiente de una notificación real de ese banco
- [x] Proceso transaccional de conciliación: acumular el consumo de un presupuesto como una
      `Compra` de negocio de verdad, en vez de recalcularlo en cada consulta a partir de
      `Comprobante` -ver [Conciliación real y bitácora en MongoDB](#conciliación-real-y-bitácora-en-mongodb)
- [x] Registro e inicio de sesión reales -ver [Registro y varios usuarios](#registro-y-varios-usuarios) más abajo
- [x] Iniciar sesión con Google, y cambiar/poner contraseña ya logueado -ver
      [Registro y varios usuarios](#registro-y-varios-usuarios)
- [ ] Roles (titular, administrador) — hoy todo titular ve y administra solo lo suyo, sin niveles
- [ ] Recuperar una contraseña olvidada -hoy hace falta estar logueado para cambiarla; si no hay
      ninguna sesión con ese correo, no hay forma de recuperar el acceso
- [x] Pruebas automatizadas de frontend -ver [Correr las pruebas y el linter](#5-correr-las-pruebas-y-el-linter)
- [ ] Desglose manual de una compra en varias líneas -`LineaCompra` ya soporta varias por `Compra`
      en el modelo, pero todavía no hay pantalla para partir un cargo; toda compra ingerida por
      correo nace con una sola línea
- [ ] Verificar en vivo la integración con el BCCR con una suscripción real. El contrato HTTP ya
      está confirmado contra la documentación del propio servicio (nombres de parámetro y formato
      de respuesta, ver la nota de conversión de moneda más arriba), pero falta la prueba de punta
      a punta: al escribirse esto el subsistema `gee.bccr.fi.cr/Indicadores/` llevaba días
      devolviendo `HTTP 503` y no se pudo ni completar la suscripción
- [ ] Publicar de verdad en App Store y Play Store -la base técnica ya está (ver arriba), pero
      faltan las cuentas de desarrollador, el hosting en producción, la verificación de OAuth y
      compilar/firmar cada app, que son trámites del titular del proyecto, no del código. Ver
      [Camino a publicar en App Store y Play Store](#camino-a-publicar-en-app-store-y-play-store).
- [ ] Cobros reales (suscripción u otro modelo) -a propósito, no se integró todavía: necesita
      cuentas de pago (Stripe, RevenueCat) con identidad fiscal real
