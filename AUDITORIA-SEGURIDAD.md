# Auditoría de seguridad · Gastonomo

**EIF509 · Laboratorio 7 — Seguridad y robustez del sistema** · II Ciclo 2026
Jose Alexis Solís Carvajal · Luis Antonio Montes de Oca Ruiz

Revisión del sistema con la lista de verificación de la Sesión 14 y con las categorías del
**OWASP Top 10:2025** que aplican a una API REST con JWT, PostgreSQL y MongoDB. Cada fila dice qué
se revisó, qué se encontró, qué riesgo tenía, qué se corrigió y en qué commit. Cuando una revisión
no encontró problemas, la fila dice **cómo se comprobó**.

> Este documento no contiene datos sensibles reales: ninguna clave, token ni URL de *deploy hook*.
> Los secretos del despliegue viven en GitHub Secrets (environment `produccion`) y en la
> plataforma, nunca en el repositorio.

**Leyenda del riesgo:** 🔴 alto · 🟠 medio · 🟡 bajo · ✅ sin hallazgo

---

## 1 · Lista de verificación de la Sesión 14

| # | Verificación | Hallazgo | Riesgo | Corrección aplicada | Commit |
|---|---|---|---|---|---|
| 1 | **Secretos fuera del código** | La clave de los JWT ya se leía del ambiente, pero sin ella la app generaba una efímera **también en producción**: cada reinicio de la plataforma deslogueaba a todos, y nada impedía una clave corta adivinable offline. Además `settings.py` arrastraba una contraseña por defecto (`demo1234`) de una cuenta demo que ya no existía. | 🟠 | Con `GASTONOMO_ENTORNO=produccion` (lo trae la imagen Docker) la app **no arranca** sin `GASTONOMO_JWT_SECRETO` de ≥ 32 caracteres. Se borraron los campos demo. La URL del despliegue va en `secrets.DEPLOY_HOOK_URL`. Se comprobó con `git grep` que ningún secreto está versionado ni hubo un `.env` en el historial. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |
| 2 | **Contraseñas con hash adaptativo** | ✅ bcrypt con costo 12 y sal por hash; el hash nunca sale en un DTO; el tope de 72 bytes de bcrypt está validado en el DTO. | ✅ | Ninguna necesaria. Comprobado en `contrasenas.py` y en `test_registrarse_es_publico_y_devuelve_201_con_location` (el cuerpo no trae `contrasena_hash`). | — |
| 3 | **Autenticación y autorización en cada endpoint** | ✅ Todo `/api/v1` exige token salvo registro y login; `exigir_rol` responde 403 por rol; la propiedad del recurso se verifica en el servicio (lo ajeno responde 404, indistinguible de lo inexistente). | ✅ | Ninguna necesaria. Comprobado por las pruebas de 401/403/404 de `test_seguridad_api.py` y `test_api_postgres.py` (p. ej. `test_404_lo_de_otro_titular_es_indistinguible_de_lo_que_no_existe`). | — |
| 4 | **Protección contra fuerza bruta en el login** | `POST /api/v1/auth/login` aceptaba intentos ilimitados contra una cuenta. | 🔴 | `LimitadorDeIntentos`: 5 fallos en 15 min bloquean esa cuenta 15 min → `429` con `Retry-After`. Se cuentan también los correos que no existen, para que el bloqueo no delate cuáles sí. Pruebas en `test_endurecimiento.py` y `test_eventos_de_seguridad.py`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) |
| 5 | **Validación de entrada y consultas parametrizadas** | ✅ Cada DTO valida formato (400); el ORM parametriza toda consulta; el `orden` de las colecciones se resuelve contra una lista cerrada de columnas. | ✅ | Ninguna necesaria. Comprobado con `git grep` (ningún `text()` con SQL armado por concatenación en `src/`) y con `paginacion.py:113`. | — |
| 6 | **Errores sin filtrar información interna** | ✅ El manejador global responde Problem Details sin trazas; el 409 de integridad no repite el mensaje del motor. El nuevo 409 de concurrencia tampoco repite el del ORM. | ✅ | Ninguna necesaria; se extendió el mismo criterio al `StaleDataError` (`test_el_stale_data_error_se_traduce_a_409_en_el_manejador_global`). | [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |
| 7 | **CORS y cabeceras de seguridad** | CORS con orígenes **fijos en el código**, `allow_credentials=True` (la API no usa cookies) y `*` en métodos y encabezados. Ninguna cabecera de seguridad en las respuestas. | 🟠 | CORS desde `GASTONOMO_ORIGENES_PERMITIDOS`, sin credenciales, con métodos y encabezados explícitos. Middleware `CabecerasDeSeguridad`: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS, CSP `default-src 'none'` y `Cache-Control: no-store` en `/api/`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`5faaf71`](https://github.com/LewMontes/Proyecto-EIF509/commit/5faaf71cadae3cf9469c4fae0ea88b06ddb60b46) |
| 8 | **Dependencias sin vulnerabilidades conocidas** | `pip-audit` encontró **37 CVE en `pillow` 12.3**, que entraba solo por `reportlab`. Ni `reportlab` ni `openpyxl` se importan en ningún módulo. | 🔴 | Se quitaron las dos dependencias. El CI corre `pip-audit` en cada push y no despliega si aparece un CVE. Comprobado en un entorno limpio: *"No known vulnerabilities found"*. | [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |

---

## 2 · OWASP Top 10:2025

| Categoría | Qué se revisó | Hallazgo | Riesgo | Corrección aplicada / cómo se comprobó | Commit |
|---|---|---|---|---|---|
| **A01 · Broken Access Control** (incluye SSRF) | Autorización por rol y por propiedad; `usuario_id` nunca aceptado del cliente; llamadas salientes. | ✅ El titular sale siempre del token. Las únicas llamadas salientes (BCCR y Hacienda) van a URLs fijas: ningún parámetro del cliente decide a dónde se conecta el servidor. | ✅ | Ver verificación 3. SSRF comprobado en `tipo_cambio_service.py:51-54`. | — |
| **A02 · Security Misconfiguration** | CORS, cabeceras, usuario del contenedor, modo producción. | CORS permisivo y sin cabeceras (verificación 7). Una imagen de `python:*-slim` sin `USER` corre la app como **root**. | 🟠 | CORS y cabeceras (verificación 7). El `Dockerfile` de despliegue crea y usa el usuario `gastonomo` (uid 10001); comprobado con `docker exec … id -un`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |
| **A03 · Software Supply Chain Failures** | Dependencias y su auditoría continua. | 37 CVE en una dependencia transitiva de una dependencia sin uso (verificación 8). | 🔴 | Ver verificación 8. | [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |
| **A04 · Cryptographic Failures** | Firma de los JWT, hash de contraseñas, datos en el token. | ✅ HS256 con `algorithms` fijado (un token `alg: none` no pasa); `exp` obligatorio. El token solo lleva `sub`, `rol`, `iat`, `exp`. Faltaba exigir una clave fuerte en producción (verificación 1). | 🟠 | Ver verificación 1. Comprobado por `test_el_token_lleva_el_titular_y_el_rol_pero_ningun_dato_sensible`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) |
| **A05 · Injection** | SQL, NoSQL (Mongo) y *log injection*. | ✅ SQL y Mongo van por el ORM y el driver con documentos, nunca con cadenas armadas. Riesgo nuevo de *log injection* al aceptar `X-Request-ID` del cliente. | 🟡 | El `X-Request-ID` del cliente se acepta solo si calza `^[A-Za-z0-9._-]{1,64}$`; si no, se genera uno (`test_el_id_de_peticion_del_cliente_se_respeta_si_es_seguro`). | [`5faaf71`](https://github.com/LewMontes/Proyecto-EIF509/commit/5faaf71cadae3cf9469c4fae0ea88b06ddb60b46) |
| **A06 · Insecure Design** | Escrituras concurrentes sobre el mismo dato. | `presupuesto.monto_consumido` se leía, sumaba y escribía desde cuatro caminos sin control: dos compras simultáneas de la misma categoría y mes **perdían una de las dos sin error** (*lost update*). | 🔴 | Bloqueo optimista: columna `version` (migración `V9`) como `version_id_col`; el conflicto sale como `409` Problem Details. Pruebas con dos transacciones reales en SQLite y PostgreSQL. | [`042d1df`](https://github.com/LewMontes/Proyecto-EIF509/commit/042d1df9c7228fb16ba6594ef2b9adfe89d0856e) · [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |
| **A07 · Authentication Failures** | Fuerza bruta, enumeración de cuentas, vida del token. | Login sin límite de intentos (verificación 4). ✅ El mensaje de error ya era el mismo para correo inexistente y contraseña equivocada; el token vive 60 minutos. | 🔴 | Ver verificación 4. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) |
| **A08 · Software or Data Integrity Failures** | Pipeline: quién despliega, con qué permisos y qué artefacto. | El workflow corría con los permisos por defecto del `GITHUB_TOKEN` y no había despliegue verificado. | 🟡 | `permissions: contents: read`; el despliegue solo corre en `push` a `master`/`main`, **después** de que `verificar` pase entero (incluida la imagen arrancada); `concurrency` evita dos despliegues a la vez. La rama protegida exige el check. | [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |
| **A09 · Security Logging and Alerting Failures** | Si un ataque deja rastro. | **No se registraba ningún evento de seguridad**: un login fallido, un 403 o un token falsificado no dejaban nada. Y `httpx` escribía en INFO la URL completa de cada petición saliente, **con el token del BCCR en la query string**. | 🔴 | Registros JSON en stdout con `id_peticion`; eventos `inicio_sesion_fallido`, `inicio_sesion_exitoso`, `inicio_sesion_bloqueado`, `acceso_no_autenticado`, `acceso_denegado` y `conflicto_de_concurrencia`, sin contraseñas ni tokens (con redacción de respaldo por nombre de campo). `httpx` bajado a WARNING. Pruebas en `test_observabilidad.py` y `test_eventos_de_seguridad.py`. | [`5faaf71`](https://github.com/LewMontes/Proyecto-EIF509/commit/5faaf71cadae3cf9469c4fae0ea88b06ddb60b46) · [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |
| **A10 · Mishandling of Exceptional Conditions** | Qué pasa cuando algo falla: base caída, conflicto, error inesperado. | ✅ El manejador global ya respondía 500 genérico y la conciliación revierte toda su transacción. Faltaba: un health check que **falle cerrado** si la base no responde, y el `StaleDataError` caía como 500. | 🟠 | `/actuator/health` responde `503 DOWN` si `SELECT 1` falla; `StaleDataError` → `409`. La app en producción tampoco arranca con configuración insegura. | [`5faaf71`](https://github.com/LewMontes/Proyecto-EIF509/commit/5faaf71cadae3cf9469c4fae0ea88b06ddb60b46) · [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |

---

## 3 · Lo que queda abierto (riesgo aceptado y declarado)

- **El límite de intentos vive en memoria del proceso.** Con una sola instancia —así se despliega—
  alcanza. Con varias, cada una contaría por separado; haría falta un almacén compartido (Redis).
- **El bloqueo por cuenta permite bloquear a otro a propósito** por 15 minutos. Es temporal, se
  registra como `inicio_sesion_bloqueado` y es el costo conocido de contar por cuenta y no por IP
  (ver el docstring de `intentos.py`).
- **Swagger UI y ReDoc siguen públicos** en producción: el Laboratorio 5 pide la documentación
  operativa y no exponen datos, solo el contrato.
- **Las acciones de GitHub están fijadas por versión mayor** (`@v4`, `@v5`) y no por SHA.
- **Los `warnings` de configuración que se emiten al importar** (antes de configurar los registros)
  salen por stderr en texto plano, no en JSON.

---

## 4 · Cómo reproducir la auditoría

```bash
pip-audit --skip-editable
```

```bash
pytest tests/test_endurecimiento.py tests/test_observabilidad.py tests/test_eventos_de_seguridad.py tests/test_concurrencia_presupuesto.py -v
```

```bash
pytest -m integracion tests/integracion/test_concurrencia_postgres.py -v
```
