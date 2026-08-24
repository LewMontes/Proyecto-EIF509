# Gastonomo · Control de gastos personales por categorías

Sistema web multiusuario donde cualquier persona crea su cuenta, vincula el buzón donde le llegan
sus comprobantes de compra, y el sistema clasifica su gasto por categoría mostrándole en vivo el
avance contra su presupuesto mensual.

**EIF509 Desarrollo de Aplicaciones Basadas en Web · II Ciclo 2026**
Universidad Nacional · Escuela de Informática y Computación

| |                                                         |
|---|---------------------------------------------------------|
| **Integrantes** | Jose Alexis Solís Carvajal · 1-1623-0238          |
|  |    Luis Antonio Montes de Oca Ruiz · 1-1800-0270     |
| **Entrega actual** | Laboratorio 2 — La capa de datos completa: PostgreSQL + MongoDB |

---

## Stack

**Python 3.14 · FastAPI · SQLAlchemy 2.0 · PostgreSQL · MongoDB · React**

> El curso recomienda Java 21 + Spring Boot 3. Este equipo solicitó y obtuvo autorización del
> profesor para usar un stack alternativo equivalente. La justificación técnica completa —con las
> alternativas descartadas y lo que la decisión nos cuesta— está en
> [ADR-001](docs/adr/ADR-001-eleccion-del-stack.md).

---

## Qué incluye este laboratorio

El **Laboratorio 2** entrega **la capa de datos completa**, con persistencia políglota:

| Entregable | Dónde está |
|---|---|
| Esquema PostgreSQL en 3FN con migraciones Flyway `V1`…`V5`, restricciones e índices justificados | [`db/postgres/migrations/`](db/postgres/migrations/) |
| Subdominio en MongoDB: la colección `bitacora_compras`, con la decisión de incrustar justificada | [`db/mongo/init/`](db/mongo/init/) · [ADR-002](docs/adr/ADR-002-subdominio-documental-en-mongodb.md) |
| Datos de ejemplo realistas en las dos bases | [`db/postgres/seeds/`](db/postgres/seeds/) · [`db/mongo/init/02_datos_de_ejemplo.js`](db/mongo/init/02_datos_de_ejemplo.js) |
| Docker Compose que levanta PostgreSQL y MongoDB con un solo comando | [`docker-compose.yml`](docker-compose.yml) |
| Documento técnico del modelo y las decisiones de diseño | [Modelo de datos](docs/modelo-de-datos.md) |

En números: **12 tablas · 17 llaves foráneas · 17 restricciones `UNIQUE` · 42 `CHECK` · 46 índices**
en PostgreSQL, más **1 colección con validador de esquema y 4 índices** en MongoDB.

El **Laboratorio 1**, que sigue en el repositorio, entregó la arquitectura por capas funcionando de
punta a punta con dos entidades (`Usuario` y `Categoria`) sobre SQLite. La aplicación **todavía usa
SQLite**: conectarla a estas dos bases es trabajo de un laboratorio siguiente.

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
configurar nada más: las credenciales de desarrollo vienen como valores por defecto (para cambiarlas,
copiá `.env.ejemplo` a `.env`).

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
parte**: la aplicación sigue usando SQLite local y crea el archivo sola al arrancar. Conectarla a las
bases de arriba es trabajo de un laboratorio siguiente.

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
| `POST` | `/api/categorias` | Crea una categoría aplicando las reglas del dominio |
| `GET` | `/api/categorias?usuario_id=1` | Lista las categorías activas de un usuario |

### 5. Correr las pruebas y el linter

```bash
pytest -v
```

```bash
ruff check . && ruff format --check .
```

Son los mismos comandos que ejecuta la integración continua. Las pruebas corren contra una base
SQLite **en memoria**, así que no tocan ningún archivo ni necesitan infraestructura.

---

## Cómo está organizado

Arquitectura en tres capas más configuración. La regla de oro:
**presentación → negocio → datos, nunca al revés.**

```
src/app/
├── presentation/   → Habla HTTP. Recibe JSON, llama al servicio, devuelve JSON.
│   ├── routers/        salud.py · categorias.py
│   ├── schemas.py      DTOs de entrada y salida
│   └── dependencies.py arma el servicio con su repositorio
│
├── business/       → Reglas del negocio. No sabe que existe HTTP.
│   ├── services/       categoria_service.py
│   └── errors.py       violaciones de reglas del dominio
│
├── data/           → Entidades y consultas. No contiene reglas de negocio.
│   ├── models/         usuario.py · categoria.py · base.py · enums.py
│   └── repositories/   el único lugar del sistema que consulta datos
│
├── config/         → Lo que cambia entre máquinas.
│   ├── settings.py     nombre, versión, URL de la base
│   └── database.py     motor, sesión y creación de tablas
│
└── main.py         → Arma la app y traduce errores de negocio a códigos HTTP.
```

La capa de datos real —lo que entrega el Laboratorio 2— vive fuera de `src/`, porque es SQL y
JavaScript de base de datos, no código de la aplicación:

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
ejecuta la suite de pruebas y **levanta el servidor de verdad** para confirmar que `/api/salud`
responde.

El estado se ve en la pestaña **Actions** del repositorio y en la insignia del inicio de este
README.

---

## Estado del proyecto

El curso son siete laboratorios incrementales sobre esta misma base. Todavía no sabemos el
contenido exacto de cada uno, así que lo pendiente queda listado sin asignarle número.

- [x] **Laboratorio 1** *(entregado)* — Arquitectura por capas, `Usuario` y `Categoria`, propuesta de dominio, CI
- [x] **Laboratorio 2** *(entregado)* — Esquema PostgreSQL con migraciones Flyway, subdominio `bitacora_compras` en MongoDB, seeds en ambas bases y Docker Compose

Pendiente para los laboratorios siguientes:

- [ ] Conectar la aplicación a PostgreSQL y MongoDB, y alinear los modelos de SQLAlchemy con el esquema migrado
- [ ] Frontend React con avance de presupuesto en vivo
- [ ] Proceso transaccional de ingesta y conciliación de comprobantes
- [ ] Autenticación, roles y vinculación del buzón de correo
