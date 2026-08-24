# ADR-003 · Flyway en lugar de Alembic para versionar el esquema

## Estado

**Aceptada** · Fecha: 23/08/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

**Supersede parcialmente a [ADR-001](ADR-001-eleccion-del-stack.md)**, que había elegido Alembic como
herramienta de migraciones.

## Contexto

ADR-001 eligió Alembic porque es la herramienta de migraciones nativa de SQLAlchemy, que es el ORM
del proyecto. Era la opción coherente con un stack Python.

El enunciado del Laboratorio 2 pide explícitamente **«migraciones Flyway (V1, V2...) que reconstruyan
la base desde cero en cualquier máquina»**. Flyway es una herramienta de la JVM, y el proyecto es
Python: nadie del equipo tiene Java instalado ni queremos exigírselo a quien clone el repositorio.

## Decisión

Usamos **Flyway 11 corriendo en su propio contenedor**, declarado como un servicio de
`docker-compose.yml` que depende del *healthcheck* de PostgreSQL. Las migraciones son **SQL plano**
en `db/postgres/migrations/`, versionadas `V1__…` a `V5__…`.

Tres consecuencias de haberlo hecho así:

1. **Nadie instala Java.** Flyway vive en su contenedor; `docker compose up -d` lo levanta, aplica lo
   que falte y lo apaga con código 0. Verlo como `Exited (0)` es el resultado correcto: es una tarea,
   no un servicio.
2. **El esquema se escribe en SQL, no se deduce de los modelos.** Es lo contrario de lo que hacía
   `crear_tablas()` en el Laboratorio 1. Escribir el DDL a mano es lo que nos permitió expresar en el
   esquema cosas que un ORM no genera solo: llaves foráneas compuestas para el aislamiento entre
   titulares, índices parciales, índices con `INCLUDE`, `CHECK` con las fórmulas del dominio y un
   índice GIN de trigramas.
3. **Los datos de ejemplo no son una migración.** Van como *callback* `afterMigrate` en una carpeta
   aparte (`db/postgres/seeds/`), porque no son parte del esquema: si fueran `V6`, Flyway los
   registraría en su historial y llevar el esquema a producción obligaría a excluir una versión a
   mano.

## Alternativas consideradas

| Opción | Por qué no |
|---|---|
| **Alembic**, como decía ADR-001 | El laboratorio pide Flyway por nombre. Además, su modo habitual es autogenerar la migración desde los modelos, y varias de las restricciones de este esquema no las produce el autogenerador. |
| **Flyway instalado en la máquina** | Obliga a instalar una JVM a cualquiera que clone el repositorio. Rompe la promesa de «un solo comando». |
| **Scripts SQL sueltos con un `psql -f`** | No hay historial ni verificación de sumas de comprobación: nada garantiza que dos máquinas quedaran con el mismo esquema, que es justo lo que la rúbrica llama *migraciones reproducibles*. |

## Consecuencias

- **A favor:** el esquema queda versionado en SQL legible y revisable en el *diff*; Flyway registra
  cada migración con su suma de comprobación en `flyway_schema_history`, así que modificar un archivo
  ya aplicado hace fallar la siguiente corrida en vez de dejar dos máquinas distintas.
- **En contra:** los modelos de SQLAlchemy (`src/app/data/models/`) y el DDL de las migraciones son
  ahora **dos fuentes que hay que mantener en sincronía a mano**. Cuando la aplicación se conecte a
  PostgreSQL —en un laboratorio siguiente— habrá que alinear los modelos con este esquema y verificar
  la equivalencia en la CI. Es el costo real de esta decisión y lo dejamos anotado.
- El Laboratorio 1 sigue funcionando igual: la aplicación conserva SQLite y `crear_tablas()` hasta
  que toque conectarla. Esta decisión afecta a la capa de datos, no a la aplicación.

## Referencias

- [`docker-compose.yml`](../../docker-compose.yml) — el servicio `flyway`.
- [Modelo de datos § 4](../modelo-de-datos.md) — cómo se levanta todo y por qué los seeds son un callback.
