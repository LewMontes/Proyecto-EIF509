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
| **Entrega actual** | Laboratorio 3 — Persistencia con ORM y repositorios |

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

El **Laboratorio 3** entrega **la capa de persistencia**: cómo la aplicación habla con el esquema
que entregó el Laboratorio 2, mediante ORM y el patrón Repository.

| Entregable | Dónde está |
|---|---|
| Mapeo objeto-relacional: 14 entidades, 20 llaves foráneas, **40 relaciones** con carga perezosa razonada | [`src/app/data/models/`](src/app/data/models/) · [Persistencia §2](docs/persistencia.md#2--el-mapeo-objeto-relacional) |
| Repositorio base genérico (`BaseRepository[TEntidad]`), 14 por entidad, más el del subdominio de MongoDB | [`src/app/data/repositories/`](src/app/data/repositories/) · [Persistencia §3](docs/persistencia.md#3--repositorios-con-generalización) |
| 4 consultas de negocio —2 estáticas y 2 dinámicas, una de ellas agregada— con el SQL que el ORM genera, documentado | [Persistencia §4](docs/persistencia.md#4--consultas-de-negocio) |
| Problema N+1 en la lista de compras: medido y corregido. **De 201 consultas a 2**, con pruebas que lo fijan | [Persistencia §5](docs/persistencia.md#5--el-problema-n1) · [`tests/test_n_mas_1.py`](tests/test_n_mas_1.py) |
| 10 pruebas de integración contra un PostgreSQL 16 real (Testcontainers), en verde en el CI | [`tests/integracion/`](tests/integracion/) · [Persistencia §6](docs/persistencia.md#6--cómo-se-prueba) |
| Documento técnico de la capa | [Persistencia](docs/persistencia.md) |

> **Lo único que queda abierto** —y está declarado, no escondido— es que la validación del mapeo
> corra contra el esquema que migra Flyway y no contra el que crea el propio mapeo. La validación en
> sí ya existe y corre en el CI; el detalle está en
> [Persistencia §7](docs/persistencia.md#7--lo-que-queda-abierto).

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

La documentación interactiva de la API se genera sola. Abrila en el navegador:

- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc

### Conectarla a PostgreSQL en vez de SQLite

Con el `docker compose up -d` de arriba corriendo, apuntá la aplicación al PostgreSQL real:

```bash
GASTONOMO_URL_BASE_DATOS=postgresql+psycopg://gastonomo:gastonomo_local@localhost:5432/gastonomo uvicorn app.main:app --app-dir src
```

En Windows (PowerShell) la variable se pone aparte:

```bash
$env:GASTONOMO_URL_BASE_DATOS = "postgresql+psycopg://gastonomo:gastonomo_local@localhost:5432/gastonomo"
```

La aplicación crea su esquema con `Base.metadata.create_all()`, **no con Flyway**. Son dos linajes
distintos y con dos tablas de diferencia; la comparación completa está en
[Persistencia §2.3](docs/persistencia.md#23--estado-del-mapeo-frente-al-esquema-del-laboratorio-2).

La bitácora de compras escribe en una base de Mongo propia (`gastonomo_app`), distinta de la que
siembra `db/mongo/init/` para el Laboratorio 2 (`gastonomo`). Si Mongo no está levantado, la
aplicación funciona igual: la bitácora explica lo que pasó, no lo decide (ver
[ADR-002](docs/adr/ADR-002-subdominio-documental-en-mongodb.md)).

### Endpoints disponibles

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/api/salud` | Confirma que el sistema está en línea |
| `POST` | `/api/categorias` | Crea una categoría aplicando las reglas del dominio |
| `GET` | `/api/categorias?usuario_id=1` | Lista las categorías activas de un titular |
| `GET` | `/api/compras?usuario_id=1` | Lista las compras del titular, más recientes primero. Con `&requiere_revision=true` trae solo las que quedaron sin método de pago o sin categoría |
| `GET` | `/api/compras/gasto-por-categoria?usuario_id=1&anio=2026&mes=9` | En qué se le fue el mes al titular, agrupado y sumado por la base. Acepta `&categoria_id=` (repetible), `&metodo_pago_id=` e `&incluir_sin_categoria=false` |
| `GET` | `/api/compras/{id}?usuario_id=1` | Detalle de una compra, con el nombre de su comercio/método/categoría ya resueltos |
| `GET` | `/api/compras/{id}/bitacora?usuario_id=1` | La trazabilidad de la compra guardada en MongoDB |

El titular se identifica con el parámetro `usuario_id`: **este repositorio todavía no tiene capa de
autenticación**, que es trabajo de un laboratorio siguiente.

### 5. Correr las pruebas y el linter

```bash
pytest -v
```

```bash
ruff check . && ruff format --check .
```

Son los mismos comandos que ejecuta la integración continua. **40 pruebas** corren contra una base
SQLite **en memoria**, así que no tocan ningún archivo ni necesitan infraestructura.

Aparte están las **10 pruebas de integración**, que levantan un PostgreSQL 16 real en Docker con
Testcontainers y lo apagan al terminar:

```bash
pytest -m integracion
```

Verifican lo que SQLite no puede detectar —`NUMERIC` decimal exacto, `ON DELETE CASCADE`, el largo
de los `VARCHAR`, el `ROLLBACK` real, y que el mapeo calce con el esquema que hay en la base. Si no
tenés Docker corriendo **se saltan solas**, no fallan. Para correr solo las rápidas:

```bash
pytest -m "not integracion"
```

El detalle de qué prueba cada una está en [Persistencia §6](docs/persistencia.md#6--cómo-se-prueba).

---

## Cómo está organizado

Arquitectura en tres capas más configuración. La regla de oro:
**presentación → negocio → datos, nunca al revés.**

```
src/app/
├── presentation/   → Habla HTTP. Recibe JSON, llama al servicio, devuelve JSON.
│   ├── routers/        salud.py · categorias.py · compras.py
│   ├── schemas.py      DTOs de entrada y salida
│   └── dependencies.py arma cada servicio con sus repositorios
│
├── business/       → Reglas del negocio. No sabe que existe HTTP.
│   ├── services/       categoria_service.py · compra_service.py ·
│   │                   bitacora_service.py (trazabilidad en MongoDB)
│   └── errors.py       violaciones de reglas del dominio
│
├── data/           → Entidades y consultas. No contiene reglas de negocio.
│   ├── models/         las 14 entidades mapeadas, más base.py · enums.py · tipos.py
│   └── repositories/   el único lugar del sistema que consulta datos:
│                       base_repository.py (genérico), 14 por entidad,
│                       y bitacora_repository.py (MongoDB)
│
├── config/         → Lo que cambia entre máquinas.
│   ├── settings.py     nombre, versión, URL de la base, Mongo
│   ├── database.py     motor, sesión por petición y creación del esquema
│   └── cliente_mongo.py cliente Mongo compartido, con su validador
│
└── main.py         → Arma la app y traduce errores de negocio a códigos HTTP.
```

El esquema que entrega el Laboratorio 2 vive fuera de `src/`, porque es SQL y JavaScript de base de
datos, no código de la aplicación:

```
db/
├── postgres/
│   ├── migrations/     → V1..V5, el historial versionado del esquema
│   └── seeds/          → datos de ejemplo (callback afterMigrate, no migración)
├── mongo/
│   └── init/           → colección bitacora_compras: validador, índices y datos
└── pruebas/            → los intentos de violar las restricciones y el validador
```

Tres decisiones sostienen la separación, ya que Python no la impone por sí solo:

1. El servicio recibe una **dataclass propia** (`CrearCategoriaComando`), no un modelo de FastAPI.
2. El repositorio **nunca confirma la transacción**: el `commit` lo hace el servicio, que es el
   único que sabe si la operación de negocio completa terminó bien.
3. Los errores de negocio son **excepciones propias** sin ninguna referencia a HTTP; `main.py` es
   el único archivo que las traduce a códigos de respuesta.

---

## Documentación

| Documento | Qué contiene |
|---|---|
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
3. Corre las 40 pruebas rápidas (`pytest -m "not integracion"`).
4. Corre las **10 pruebas de integración contra un PostgreSQL real**: Testcontainers levanta el
   contenedor dentro del propio runner, así que no hace falta declarar ningún `services:`.
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

Pendiente para los laboratorios siguientes:

- [ ] Que la validación del mapeo corra contra el esquema migrado por Flyway y no contra el que crea
      el propio mapeo ([Persistencia §7](docs/persistencia.md#7--lo-que-queda-abierto))
- [ ] Autenticación y roles: hoy el titular se identifica con un `usuario_id` en la petición
- [ ] Frontend con avance de presupuesto en vivo
- [ ] Proceso transaccional de ingesta y conciliación de comprobantes de correo
