# Gastonomo · Control de gastos personales por categorías

[![CI](https://github.com/LewMontes/Proyecto-EIF509/actions/workflows/ci.yml/badge.svg)](https://github.com/LewMontes/Proyecto-EIF509/actions/workflows/ci.yml)

Sistema web multiusuario donde cualquier persona registra su gasto, lo clasifica por categoría y ve
en vivo el avance contra su presupuesto mensual.

**EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026**
Universidad Nacional · Escuela de Informática y Computación

| |                                                         |
|---|---------------------------------------------------------|
| **Integrantes** | Jose Alexis Solís Carvajal · 1-1623-0238          |
|  |    Luis Antonio Montes de Oca Ruiz · 1-1800-0270     |
| **Entrega actual** | Laboratorio 5 — API REST y servicios web |

---

## Stack

**Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL · MongoDB**

> El curso recomienda Java 21 + Spring Boot 3. Este equipo solicitó y obtuvo autorización del
> profesor para usar un stack alternativo equivalente. La justificación técnica completa —con las
> alternativas descartadas y lo que la decisión nos cuesta— está en
> [ADR-001](docs/adr/ADR-001-eleccion-del-stack.md).
>
> La correspondencia término por término entre JPA/Hibernate y SQLAlchemy —`@Entity`,
> `FetchType.LAZY`, JPQL, Criteria, `JOIN FETCH`, `ddl-auto=validate`— está en la tabla que abre
> [Persistencia](docs/persistencia.md).

---

## Qué incluye este laboratorio

El **Laboratorio 5** expone la capa de negocio como **una API REST profesional**: un contrato
versionado y documentado, con semántica HTTP correcta, errores estándar, colecciones paginadas y
seguridad con JWT y roles, verificado con pruebas de integración.

| Entregable | Dónde está |
|---|---|
| Endpoints REST versionados bajo `/api/v1`: las entidades principales y los dos procesos, con `201` + `Location`, `204`, `404`, `409` y `422` | [`presentation/routers/`](src/app/presentation/routers/) · [API §1](docs/api.md#1--diseño-rest) |
| Manejo global de errores con Problem Details (RFC 9457) y validación de formato en los DTOs; ninguna traza expuesta | [`errores.py`](src/app/presentation/errores.py) · [`schemas.py`](src/app/presentation/schemas.py) · [API §3](docs/api.md#3--errores-estándar-y-validación) |
| Colecciones paginadas con metadatos, orden por parámetro y diez filtros de negocio con *Specifications* | [`paginacion.py`](src/app/data/paginacion.py) · [`especificaciones.py`](src/app/data/repositories/especificaciones.py) · [API §4](docs/api.md#4--paginación-orden-y-filtros) |
| Seguridad: `POST /api/v1/auth/login`, API *stateless*, dos roles con autorización por endpoint y propiedad del recurso verificada en el servicio | [`dependencies.py`](src/app/presentation/dependencies.py) · [`auth_service.py`](src/app/business/services/auth_service.py) · [API §5](docs/api.md#5--seguridad) |
| Documentación OpenAPI con Swagger UI operativa, y una colección `.http` que ejercita las 42 operaciones | `/docs` · [`docs/api/gastonomo.http`](docs/api/gastonomo.http) |
| Pruebas de integración de la API con Testcontainers: `201`, `400`, `401`, `403`, `404`, `409` y `422` | [`test_api_postgres.py`](tests/integracion/test_api_postgres.py) · [API §7](docs/api.md#7--pruebas-de-integración) |
| Documento técnico del contrato | [API REST](docs/api.md) |

**La retroalimentación del Laboratorio 4** se atendió completa en esta misma entrega: el Proceso 2
quedó conectado con la aplicación, las reglas se alinearon con la propuesta, los patrones se
implementaron como tales y se agregaron las pruebas con dobles. El detalle, sugerencia por
sugerencia, está en [Capa de negocio §9](docs/negocio.md#9--respuesta-a-la-retroalimentación-del-laboratorio-4).

El **Laboratorio 4**, que sigue en el repositorio, entregó **la capa de negocio completa**: los dos procesos del dominio como
servicios con reglas, la garantía transaccional del proceso multi-paso, la frontera de DTOs y los
patrones de diseño aplicados.

| Entregable | Dónde está |
|---|---|
| Proceso 1 · registro manual de una compra con desglose por renglón | [`registrar_compra_service.py`](src/app/business/services/registrar_compra_service.py) · `POST /api/v1/compras` |
| Proceso 2 · conciliación de un comprobante, en una sola transacción de cinco tablas | [`conciliacion_service.py`](src/app/business/services/conciliacion_service.py) · `POST /api/v1/comprobantes` |
| Excepciones propias del dominio, sin ninguna referencia a HTTP | [`errors.py`](src/app/business/errors.py) · traducidas solo en [`errores.py`](src/app/presentation/errores.py) |
| Prueba de *rollback*: el fallo se provoca **dentro** del servicio, contra PostgreSQL real | [`test_rollback_conciliacion.py`](tests/integracion/test_rollback_conciliacion.py) |
| Frontera DTO: comandos de entrada y resultados de salida, con mapeo manual | [`schemas.py`](src/app/presentation/schemas.py) · las dataclasses de `business/` |
| Dos patrones de diseño, con la señal que justificó cada uno | [Capa de negocio §6](docs/negocio.md#6--patrones-de-diseño-aplicados) |
| 220 pruebas unitarias de las reglas -61 de ellas con dobles-, con cobertura medida en el CI (94 %, umbral 70 %) | [`tests/`](tests/) · [`tests/unitarias/`](tests/unitarias/) |
| Migraciones `V6` y `V7`: los cambios de esquema que exige la capa de negocio | [`db/postgres/migrations/`](db/postgres/migrations/) |
| Documento técnico de la capa | [Capa de negocio](docs/negocio.md) |

> **Lo que queda abierto** está declarado, no escondido, en
> [Capa de negocio §8](docs/negocio.md#8--lo-que-queda-abierto) y en
> [API §8](docs/api.md#8--lo-que-queda-abierto).

El **Laboratorio 3**, que sigue en el repositorio, entregó **la capa de persistencia**: cómo la
aplicación habla con el esquema que entregó el Laboratorio 2, mediante ORM y el patrón Repository.

| Entregable | Dónde está |
|---|---|
| Mapeo objeto-relacional: 14 entidades, 20 llaves foráneas, **40 relaciones** con carga perezosa razonada | [`src/app/data/models/`](src/app/data/models/) · [Persistencia §2](docs/persistencia.md#2--el-mapeo-objeto-relacional) |
| Repositorio base genérico (`BaseRepository[TEntidad]`), 14 por entidad, más el del subdominio de MongoDB | [`src/app/data/repositories/`](src/app/data/repositories/) · [Persistencia §3](docs/persistencia.md#3--repositorios-con-generalización) |
| 4 consultas de negocio —2 estáticas y 2 dinámicas, una de ellas agregada— con el SQL que el ORM genera, documentado | [Persistencia §4](docs/persistencia.md#4--consultas-de-negocio) |
| Problema N+1 en la lista de compras: medido y corregido. **De 201 consultas a 2**, con pruebas que lo fijan | [Persistencia §5](docs/persistencia.md#5--el-problema-n1) · [`tests/test_n_mas_1.py`](tests/test_n_mas_1.py) |
| 14 pruebas de integración contra un PostgreSQL 16 real (Testcontainers), en verde en el CI | [`tests/integracion/`](tests/integracion/) · [Persistencia §6](docs/persistencia.md#6--cómo-se-prueba) |
| Documento técnico de la capa | [Persistencia](docs/persistencia.md) |

El **Laboratorio 2**, que sigue en el repositorio, entregó **la capa de datos**, con persistencia
políglota:

| Entregable | Dónde está |
|---|---|
| Esquema PostgreSQL en 3FN con migraciones Flyway `V1`…`V5`, restricciones e índices justificados | [`db/postgres/migrations/`](db/postgres/migrations/) |
| Subdominio en MongoDB: la colección `bitacora_compras`, con la decisión de incrustar justificada | [`db/mongo/init/`](db/mongo/init/) · [ADR-002](docs/adr/ADR-002-subdominio-documental-en-mongodb.md) |
| Datos de ejemplo realistas en las dos bases | [`db/postgres/seeds/`](db/postgres/seeds/) · [`db/mongo/init/02_datos_de_ejemplo.js`](db/mongo/init/02_datos_de_ejemplo.js) |
| Docker Compose que levanta PostgreSQL, Flyway y MongoDB con un solo comando | [`docker-compose.yml`](docker-compose.yml) |
| Documento técnico del modelo y las decisiones de diseño | [Modelo de datos](docs/modelo-de-datos.md) |

En números: **12 tablas · 17 llaves foráneas · 17 restricciones `UNIQUE` · 42 `CHECK` · 46 índices**
en PostgreSQL, más **1 colección con validador de esquema y 4 índices** en MongoDB.

El **Laboratorio 1** entregó la arquitectura por capas funcionando de punta a punta con dos
entidades (`Usuario` y `Categoria`) sobre SQLite.

El dominio completo está diseñado y documentado en la
[Propuesta de Dominio](docs/propuesta-dominio.md).

---

## Cómo levantar las bases de datos

Necesitás **Docker Desktop**. Desde la raíz del repositorio:

```bash
docker compose up -d
```

Eso levanta PostgreSQL, aplica las cinco migraciones de Flyway con sus datos de ejemplo, y levanta
MongoDB con la colección `bitacora_compras` creada, validada, indexada y sembrada. No hay que
configurar nada más: las credenciales de desarrollo vienen como valores por defecto (para
cambiarlas, copiá `.env.ejemplo` a `.env`).

Comprobá que todo quedó arriba:

```bash
docker compose ps -a
```

`gastonomo-postgres` y `gastonomo-mongo` deben decir `Up (healthy)`, y **`gastonomo-flyway` debe
decir `Exited (0)`**: es una tarea que migra y se apaga, no un servicio.

Mirá los datos de PostgreSQL:

```bash
docker compose exec postgres psql -U gastonomo -d gastonomo -c "\dt"
```

Y los de MongoDB:

```bash
docker compose exec mongo mongosh --quiet -u gastonomo -p gastonomo_local --authenticationDatabase admin gastonomo --eval "db.bitacora_compras.findOne({compra_id: NumberLong(7)})"
```

Para borrar todo y empezar de cero:

```bash
docker compose down -v
```

### Comprobar que las restricciones hacen su trabajo

Doce intentos de meter datos que el dominio prohíbe. Los doce deben salir como `RECHAZADO OK`:

```bash
docker compose exec -T postgres psql -U gastonomo -d gastonomo -q < db/pruebas/restricciones_postgres.sql
```

Seis intentos contra el validador de MongoDB, más las consultas que justifican el diseño de la
colección:

```bash
docker compose exec -T mongo mongosh --quiet -u gastonomo -p gastonomo_local --authenticationDatabase admin gastonomo < db/pruebas/validador_mongo.js
```

---

## Cómo correr la aplicación

Necesitás **Python 3.12 o superior** (nosotros usamos 3.14). **No hace falta Docker para esta
parte**: por defecto la aplicación usa un SQLite local y crea el archivo sola al arrancar.

### 1. Clonar y crear el entorno virtual

```bash
git clone https://github.com/LewMontes/Proyecto-EIF509.git
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

El resto de la API exige un token. El recorrido mínimo -registrarse, iniciar sesión y usar el
token-:

```bash
curl -X POST http://localhost:8000/api/v1/usuarios -H "Content-Type: application/json" -d '{"nombre_completo":"Ana Mora","correo":"ana@gastonomo.cr","contrasena":"una-clave-larga"}'
```

```bash
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d '{"correo":"ana@gastonomo.cr","contrasena":"una-clave-larga"}'
```

```bash
curl http://localhost:8000/api/v1/categorias -H "Authorization: Bearer <access_token>"
```

Más cómodo que `curl`:

- **Swagger UI** → http://localhost:8000/docs. Pegá el `access_token` en **Authorize** y probá
  cualquier endpoint desde la página.
- **La colección** [`docs/api/gastonomo.http`](docs/api/gastonomo.http), con la extensión *REST
  Client* de VS Code: ejercita las 42 operaciones de arriba hacia abajo.
- **ReDoc** → http://localhost:8000/redoc

#### Variables de seguridad

| Variable | Para qué | Sin ella |
|---|---|---|
| `GASTONOMO_JWT_SECRETO` | Clave con la que se firman los tokens | Se genera una temporal en cada arranque: los tokens dejan de valer al reiniciar |
| `GASTONOMO_JWT_MINUTOS` | Minutos de vida de cada token | `60` |
| `GASTONOMO_ADMIN_CORREO` · `GASTONOMO_ADMIN_CONTRASENA` | La cuenta `ADMIN` que se crea al arrancar | No existe ningún administrador. Registrarse por la API siempre crea un `TITULAR` |

Para tener un administrador con el que probar los endpoints de `ADMIN`:

```bash
GASTONOMO_ADMIN_CORREO=admin@gastonomo.cr GASTONOMO_ADMIN_CONTRASENA=clave-de-admin-123 uvicorn app.main:app --reload --app-dir src
```

En Windows (PowerShell) las variables se ponen aparte, antes de levantar:

```bash
$env:GASTONOMO_ADMIN_CORREO = "admin@gastonomo.cr"; $env:GASTONOMO_ADMIN_CONTRASENA = "clave-de-admin-123"
```

### Conectarla a PostgreSQL en vez de SQLite

Con el `docker compose up -d` de arriba corriendo, apuntá la aplicación al PostgreSQL real:

```bash
GASTONOMO_URL_BASE_DATOS=postgresql+psycopg://gastonomo:gastonomo_local@localhost:5432/gastonomo uvicorn app.main:app --app-dir src
```

En Windows (PowerShell) la variable se pone aparte:

```bash
$env:GASTONOMO_URL_BASE_DATOS = "postgresql+psycopg://gastonomo:gastonomo_local@localhost:5432/gastonomo"
```

La aplicación crea su esquema con `Base.metadata.create_all()` al arrancar, así que hay que
apuntarla a una base **vacía**, no a la que ya migró Flyway. El mapeo y las migraciones describen el
mismo esquema -lo verifican las pruebas de integración, que corren contra `V1`…`V8`-; el detalle está
en [Persistencia §2.3](docs/persistencia.md#23--estado-del-mapeo-frente-al-esquema-del-laboratorio-2).

La bitácora de compras escribe en una base de Mongo propia (`gastonomo_app`), distinta de la que
siembra `db/mongo/init/` para el Laboratorio 2 (`gastonomo`). Si Mongo no está levantado, la
aplicación funciona igual: la bitácora explica lo que pasó, no lo decide (ver
[ADR-002](docs/adr/ADR-002-subdominio-documental-en-mongodb.md)).

### Endpoints disponibles

42 operaciones bajo `/api/v1`. La tabla completa -con el rol que exige cada una y su código de
éxito- está en [API §1.2](docs/api.md#12--los-recursos); este es el resumen por recurso:

| Recurso | Operaciones | Notas |
|---|---|---|
| `/api/salud` | `GET` | Público y sin versión |
| `/api/v1/auth/login` | `POST` | Público. Emite el JWT |
| `/api/v1/usuarios` | `POST` · `GET` · `GET /yo` · `GET /{id}` | Registrarse es público; listar es de `ADMIN` |
| `/api/v1/categorias` | `POST` · `GET` · `GET /{id}` · `PUT /{id}` · `DELETE /{id}` | |
| `/api/v1/comercios` | `POST` · `GET` · `GET /{id}` · `PUT /{id}/categoria-sugerida` | El alta es de `ADMIN`. Paginada |
| `/api/v1/metodos-pago` | `POST` · `GET` · `GET /{id}` · `DELETE /{id}` | |
| `/api/v1/presupuestos` | `POST` · `GET` · `GET /{id}` · `PUT /{id}` · `DELETE /{id}` | |
| `/api/v1/reglas-categorizacion` | `POST` · `GET` · `GET /{id}` · `DELETE /{id}` | |
| `/api/v1/compras` | `POST` · `GET` · `GET /{id}` · `PATCH /{id}` · `DELETE /{id}` · `GET /{id}/bitacora` · `GET /gasto-por-categoria` | **Proceso 1.** Paginada, ordenable y con filtros |
| `/api/v1/cuentas-correo` | `POST` · `GET` · `GET /{id}` | |
| `/api/v1/comprobantes` | `POST` · `GET` · `GET /{id}` · `POST /{id}/reintentos` | **Proceso 2.** Paginada |

El titular sale siempre del token: **ningún endpoint acepta `usuario_id`**.

### 5. Correr las pruebas y el linter

```bash
pytest -v
```

```bash
ruff check . && ruff format --check .
```

Son los mismos comandos que ejecuta la integración continua. **407 pruebas** corren contra una
base SQLite **en memoria** o directamente con dobles, así que no tocan ningún archivo ni necesitan
infraestructura.

Aparte están las **55 pruebas de integración**, que levantan un PostgreSQL 16 real en Docker con
Testcontainers, le aplican las migraciones de Flyway (`V1`…`V8`) y lo apagan al terminar:

```bash
pytest -m integracion
```

Verifican lo que SQLite no puede detectar —`NUMERIC` decimal exacto, `ON DELETE CASCADE`, el largo
de los `VARCHAR`, el `ROLLBACK` real, que el mapeo calce con el esquema de Flyway, y **los códigos de
estado de la API de punta a punta**. Si no tenés Docker corriendo **se saltan solas**, no fallan. Para correr solo las rápidas:

```bash
pytest -m "not integracion"
```

El detalle de qué prueba cada una está en [Persistencia §6](docs/persistencia.md#6--cómo-se-prueba),
[Capa de negocio §7](docs/negocio.md#7--cómo-se-prueba) y [API §7](docs/api.md#7--pruebas-de-integración).

---

## Cómo está organizado

Arquitectura en tres capas más configuración. La regla de oro:
**presentación → negocio → datos, nunca al revés.**

```
src/app/
├── presentation/   → Habla HTTP. Recibe JSON, llama al servicio, devuelve JSON.
│   ├── routers/        un archivo por recurso: auth · usuarios · categorias · comercios ·
│   │                   metodos_pago · presupuestos · reglas_categorizacion · compras ·
│   │                   cuentas_correo · comprobantes · salud
│   ├── schemas.py      DTOs de entrada y salida, con su validación de formato
│   ├── errores.py      el manejador global: todo error sale como Problem Details
│   ├── paginacion.py   los parámetros de página y el sobre de respuesta
│   ├── rutas.py        la versión del contrato (/api/v1), en un solo lugar
│   └── dependencies.py arma cada servicio, y la cadena de seguridad (token y rol)
│
├── business/       → Reglas del negocio. No sabe que existe HTTP.
│   ├── services/       los dos procesos, los servicios de catálogo, la autenticación,
│   │                   la cadena de categorización y el State del comprobante
│   ├── seguridad/      contrasenas.py (bcrypt) · tokens.py (JWT)
│   └── errors.py       familias de error y una excepción con nombre por regla
│
├── data/           → Entidades y consultas. No contiene reglas de negocio.
│   ├── models/         las 14 entidades mapeadas, más base.py · enums.py · tipos.py
│   ├── repositories/   el único lugar del sistema que consulta datos:
│   │                   base_repository.py (genérico), 14 por entidad,
│   │                   especificaciones.py (filtros componibles)
│   │                   y bitacora_repository.py (MongoDB)
│   └── paginacion.py   SolicitudDePagina · Pagina · paginar
│
├── config/         → Lo que cambia entre máquinas.
│   ├── settings.py     nombre, versión, URL de la base, Mongo, clave de los JWT
│   ├── database.py     motor, sesión por petición, esquema y siembra del administrador
│   └── cliente_mongo.py cliente Mongo compartido, con su validador
│
└── main.py         → Arma la app: routers, manejadores de error y contrato OpenAPI.
```

El esquema que entrega el Laboratorio 2 vive fuera de `src/`, porque es SQL y JavaScript de base de
datos, no código de la aplicación:

```
db/
├── postgres/
│   ├── migrations/     → V1..V8, el historial versionado del esquema
│   └── seeds/          → datos de ejemplo (callback afterMigrate, no migración)
├── mongo/
│   └── init/           → colección bitacora_compras: validador, índices y datos
└── pruebas/            → los intentos de violar las restricciones y el validador
```

Tres decisiones sostienen la separación, ya que Python no la impone por sí solo:

1. El servicio recibe una **dataclass propia** (`CrearCategoriaComando`), no un modelo de FastAPI.
2. El repositorio **nunca confirma la transacción**: el `commit` lo hace el servicio, que es el
   único que sabe si la operación de negocio completa terminó bien.
3. Los errores de negocio son **excepciones propias** sin ninguna referencia a HTTP;
   `presentation/errores.py` es el único archivo que las traduce a códigos de respuesta.

---

## Documentación

| Documento | Qué contiene |
|---|---|
| [API REST](docs/api.md) | **Laboratorio 5.** El contrato público: diseño de los recursos, Problem Details, paginación y *Specifications*, seguridad con JWT y roles, OpenAPI y las pruebas de integración. |
| [Capa de negocio](docs/negocio.md) | **Laboratorio 4.** Los dos procesos como servicios con sus reglas, la transacción de cinco tablas, la frontera de DTOs, los dos patrones de diseño con la señal que los justificó, y lo que queda abierto. |
| [Persistencia](docs/persistencia.md) | **Laboratorio 3.** El mapeo objeto-relacional, los repositorios con generalización, las consultas de negocio con su SQL generado, la evidencia del N+1 y lo que queda abierto. |
| [Modelo de datos](docs/modelo-de-datos.md) | **Laboratorio 2.** El esquema relacional, su normalización, sus restricciones e índices justificados, y el subdominio de MongoDB con su justificación completa. |
| [Propuesta de Dominio](docs/propuesta-dominio.md) | El negocio, los actores, las entidades y los 2 procesos con sus reglas, cálculos y validaciones. |
| [Arquitectura](docs/arquitectura.md) | Diagramas de capas, recorrido de una petición, modelo entidad-relación y despliegue previsto. |
| [ADR-001 · Elección del stack](docs/adr/ADR-001-eleccion-del-stack.md) | Por qué Python + FastAPI + PostgreSQL, qué descartamos y qué nos cuesta. |
| [ADR-002 · Subdominio documental](docs/adr/ADR-002-subdominio-documental-en-mongodb.md) | Por qué la trazabilidad de la compra va en MongoDB incrustada, qué candidatos descartamos y qué invalidaría la decisión. |
| [ADR-003 · Flyway para las migraciones](docs/adr/ADR-003-flyway-para-las-migraciones.md) | Por qué Flyway en un contenedor en lugar de Alembic, y qué nos cuesta. |

---

## Integración continua

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre en cada push y en cada pull request
sobre `main` y `master`. En una máquina limpia:

1. Instala el proyecto y sus dependencias de desarrollo.
2. Revisa el código con `ruff check` y `ruff format --check`.
3. Corre las 407 pruebas rápidas midiendo la cobertura de la capa de negocio
   (`pytest -m "not integracion" --cov`), con umbral del 70 %: si baja de ahí, el paso falla.
4. Corre las **55 pruebas de integración contra un PostgreSQL real** con el esquema de Flyway:
   Testcontainers levanta el contenedor dentro del propio runner, así que no hace falta declarar
   ningún `services:`.
5. **Levanta el servidor de verdad** con uvicorn y confirma que `/api/salud` responde.

El estado se ve en la pestaña **Actions** del repositorio y en la insignia del inicio de este
README.

---

## Estado del proyecto

El curso son siete laboratorios incrementales sobre esta misma base. Todavía no sabemos el
contenido exacto de cada uno, así que lo pendiente queda listado sin asignarle número.

- [x] **Laboratorio 1** *(entregado)* — Arquitectura por capas, `Usuario` y `Categoria`, propuesta
      de dominio, CI
- [x] **Laboratorio 2** *(entregado)* — Esquema PostgreSQL con migraciones Flyway, subdominio
      `bitacora_compras` en MongoDB, seeds en ambas bases y Docker Compose
- [x] **Laboratorio 3** *(entregado)* — Las 14 entidades mapeadas con sus 40 relaciones y carga
      perezosa razonada, repositorio base genérico más 14 específicos y el del subdominio de
      MongoDB, 4 consultas de negocio con su SQL documentado, el N+1 de la lista de compras medido
      y corregido (201 consultas → 2) y 10 pruebas de integración contra PostgreSQL real con
      Testcontainers. Ver [Persistencia](docs/persistencia.md).

- [x] **Laboratorio 4** *(entregado)* — La capa de negocio: los dos procesos del dominio como
      servicios con reglas, la transacción de cinco tablas con su prueba de *rollback*, la frontera
      de DTOs y los patrones de diseño. Ver [Capa de negocio](docs/negocio.md).
- [x] **Laboratorio 5** *(esta entrega)* — API REST versionada (`/api/v1`) con Problem Details,
      colecciones paginadas con *Specifications*, seguridad JWT con dos roles, OpenAPI y pruebas de
      integración de los códigos de estado. Y la retroalimentación del Laboratorio 4, atendida
      completa. Ver [API REST](docs/api.md).

Pendiente para los laboratorios siguientes:

- [ ] Frontend con avance de presupuesto en vivo
- [ ] Enlazar los buzones con el proveedor (OAuth2) para que el sistema lea el correo solo: hoy el
      comprobante entra ya leído por `POST /api/v1/comprobantes`
