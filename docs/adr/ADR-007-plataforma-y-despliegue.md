# ADR-007 · Plataforma y despliegue: contenedor en Render, desplegado solo por el pipeline

## Estado y fecha

**Aceptada** · Fecha: 25/10/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

Tomada en el Laboratorio 7. Registrada en la Sesión 15.

## Contexto

El sistema tiene que estar **en la nube, estable y demostrable** para la defensa, y el pipeline
tiene que impedir que un cambio con errores llegue a producción. Las restricciones:

- Dos estudiantes, sin presupuesto para infraestructura ni tiempo para administrar un servidor.
- La API necesita PostgreSQL; MongoDB es opcional por diseño, porque la bitácora explica y no decide
  ([ADR-002](ADR-002-subdominio-documental-en-mongodb.md)).
- Ningún secreto puede quedar en el repositorio: clave JWT, URL de la base, *deploy hook*.
- El CI ya corría ruff, las pruebas y la integración contra PostgreSQL real, pero nada desplegaba
  ni comprobaba que lo desplegado arrancara.

## Decisión

Desplegamos la API como **un contenedor Docker en Render** (una instancia, plan gratuito), con un
**PostgreSQL administrado por la plataforma**. **Solo el pipeline despliega**: el trabajo `desplegar`
corre en un `push` a `master`/`main`, después de que `verificar` pase entero, llama al *deploy hook* y
espera a que producción responda `UP` en `/actuator/health`.

Cómo se arma:

| Pieza | Dónde | Qué hace |
|---|---|---|
| Imagen | [`Dockerfile`](../../Dockerfile) | `python:3.14-slim`, usuario sin privilegios (uid 10001), `GASTONOMO_ENTORNO=produccion`, `HEALTHCHECK` contra `/actuator/health`, puerto desde `$PORT` |
| `verificar` | [`ci.yml`](../../.github/workflows/ci.yml) | ruff · `pip-audit` · pruebas con cobertura ≥ 70 % en negocio · integración con Testcontainers · construye la imagen, la arranca en modo producción y exige `UP` |
| `desplegar` | [`ci.yml`](../../.github/workflows/ci.yml) | `needs: verificar`, nunca en un PR, `concurrency` para no desplegar dos a la vez, permisos `contents: read` |
| Secretos | GitHub → environment `produccion` y variables de la plataforma | `DEPLOY_HOOK_URL`, `GASTONOMO_JWT_SECRETO`, `GASTONOMO_URL_BASE_DATOS`, `GASTONOMO_ORIGENES_PERMITIDOS` |
| Rama protegida | GitHub → *Branches* | Exige pull request y el check `verificar` para fusionar en `master` |

El despliegue automático propio de Render está **apagado**, y la documentación de la API se cierra
en producción salvo que `GASTONOMO_DOCS_PUBLICAS=true` (por ejemplo, para la defensa). El paso a paso
está en el [README § Despliegue](../../README.md#despliegue).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| **Despliegue automático de la plataforma** en cada push | Render publicaría `master` aunque el pipeline estuviera en rojo. Que despliegue solo `desplegar`, con `needs: verificar`, es lo que impide que un cambio con errores llegue a producción. |
| **Runtime nativo de Python** de la plataforma, sin Docker | El CI no podría probar el artefacto que se publica. Con el `Dockerfile`, una receta rota se descubre en `verificar` y no en la plataforma. |
| **Un servidor propio** (VPS) con `docker compose` | Habría que administrar sistema operativo, parches, TLS y respaldos de la base. Con dos personas y sin presupuesto, ese tiempo no lo tenemos. |
| **Publicar la imagen en un registro** (GHCR) y que la plataforma la descargue | Sería desplegar exactamente el mismo binario que probó el CI, pero suma un registro y sus credenciales al pipeline. Se prefirió que la plataforma construya desde la misma receta y el mismo commit de `master`. |

## Consecuencias

**Lo que se gana**

- Nada llega a producción sin pasar lint, auditoría de dependencias, pruebas, integración y una
  imagen arrancada de verdad.
- Ninguna credencial vive en el repositorio; en producción la app **no arranca** con una clave JWT
  débil ni con `*` en CORS.
- `/actuator/health` falla cerrado (`503 DOWN` si la base no responde), y lo usan la plataforma, el
  `HEALTHCHECK` de la imagen y el pipeline.
- Los registros JSON salen por stdout y los recoge la plataforma, con un `id_peticion` por petición.

**Lo que se asume**

- **El plan gratuito duerme el servicio.** El primer pedido después de un rato tarda en responder, y
  por eso el pipeline espera hasta 15 minutos. Antes de la defensa hay que despertarlo.
- **Una sola instancia.** No hay escalado horizontal; el límite de intentos de login en memoria
  depende de eso ([ADR-006](ADR-006-autenticacion-jwt-stateless.md)).
- **La plataforma reconstruye la imagen.** Es la misma receta y el mismo commit, pero no el mismo
  binario que probó `verificar`.
- **En producción el esquema lo crea `Base.metadata.create_all()` al arrancar, no Flyway.** Las
  migraciones `V1`…`V9` se verifican contra el mapeo en las pruebas de integración, pero no son lo
  que se aplica en el despliegue.
- **MongoDB no forma parte del despliegue descrito.** `GASTONOMO_MONGO_URL` no está entre las
  variables de la plataforma del README: sin una instancia accesible la API funciona igual, pero la
  bitácora queda inactiva. Para mostrar la trazabilidad en la nube hace falta una instancia
  administrada y definir esa variable.
- Dependemos de Render: el *deploy hook*, el `$PORT` y su proxy (`--proxy-headers`) son propios de
  la plataforma, aunque la imagen corre igual en cualquier lugar con Docker.
