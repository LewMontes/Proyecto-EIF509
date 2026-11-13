# Registros de decisión de arquitectura (ADR)

Las cinco decisiones que pide la plantilla de la Sesión 15, y el registro que responde a cada una.
Todos siguen las secciones de la plantilla: título, estado y fecha, contexto, decisión,
alternativas consideradas y consecuencias.

| # | Decisión del proyecto | Registro |
|---|---|---|
| 1 | El dominio y su alcance | [ADR-004 · Dominio y alcance](ADR-004-dominio-y-alcance.md) |
| 2 | SQL o NoSQL para cada subdominio | [ADR-002 · Subdominio documental en MongoDB](ADR-002-subdominio-documental-en-mongodb.md) |
| 3 | Los patrones de diseño aplicados | [ADR-005 · Patrones de diseño](ADR-005-patrones-de-diseno.md) |
| 4 | La estrategia de autenticación | [ADR-006 · Autenticación JWT *stateless*](ADR-006-autenticacion-jwt-stateless.md) |
| 5 | La plataforma y la estrategia de despliegue | [ADR-007 · Plataforma y despliegue](ADR-007-plataforma-y-despliegue.md) |

Los números siguen el orden en que se escribió cada registro, no el de la lista: ADR-001 a ADR-003
son de los dos primeros laboratorios, y ADR-004 a ADR-007 se registraron en la Sesión 15 a partir de
decisiones que ya estaban en el código y en la documentación.

## Otros registros

| Registro | Decisión |
|---|---|
| [ADR-001 · Elección del stack](ADR-001-eleccion-del-stack.md) | Python + FastAPI + PostgreSQL en lugar de Java + Spring Boot |
| [ADR-003 · Flyway para las migraciones](ADR-003-flyway-para-las-migraciones.md) | Flyway en su propio contenedor en lugar de Alembic |
