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

| # | Verificación (lámina 28) | Hallazgo | Riesgo | Corrección aplicada / cómo se comprobó | Commit |
|---|---|---|---|---|---|
| 1 | **Un usuario no puede ver ni modificar recursos de otro** | ✅ Todo `/api/v1` exige token; el `usuario_id` sale siempre del token, nunca de la URL ni del cuerpo, y cada servicio busca el recurso con `obtener_de_usuario(id, usuario_id)`. Lo ajeno responde 404, indistinguible de lo inexistente. | ✅ | Comprobado como pide la lámina —el identificador de otro titular con un token válido— en `test_404_lo_de_otro_titular_es_indistinguible_de_lo_que_no_existe` y `test_403_un_titular_no_consulta_la_cuenta_de_otro` (`tests/integracion/test_api_postgres.py`). | — |
| 2 | **Ningún endpoint devuelve una entidad JPA** (aquí, de SQLAlchemy) | ✅ Cada endpoint declara un DTO `*Response` como `response_model`; las entidades no cruzan la capa de presentación. | ✅ | Comprobado recorriendo el contrato OpenAPI: 42 de 43 operaciones devuelven un DTO; la otra es `/actuator/health`, que devuelve un literal. Ningún esquema expone `contrasena_hash`. | — |
| 3 | **No hay consultas construidas concatenando texto** | ✅ Todas las consultas van por el ORM con parámetros; los filtros se componen con *Specifications* y el `orden` se resuelve contra una lista cerrada de columnas. | ✅ | `git grep` en `src/`: ninguna consulta armada con `+` ni con f-strings. Lista cerrada en `src/app/data/paginacion.py`. | — |
| 4 | **Los errores no envían la traza al cliente** | ✅ El manejador global responde siempre Problem Details; un 500 dice solo «error inesperado» y la traza va al registro. El 409 de integridad y el de concurrencia tampoco repiten el mensaje del motor o del ORM. | ✅ | Probado en `tests/test_errores_api.py` y en `test_el_stale_data_error_se_traduce_a_409_en_el_manejador_global`. | [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |
| 5 | **CORS solo permite el dominio de la SPA** | CORS tenía orígenes fijos en el código, credenciales y `*` en métodos y encabezados. Corregido eso, **en producción seguía aceptando `http://localhost:5173`**, porque era el valor por defecto y la plataforma no definía otro. | 🟠 | Orígenes desde `GASTONOMO_ORIGENES_PERMITIDOS`, sin credenciales y con métodos y encabezados explícitos; en producción, sin la variable, la lista queda vacía, y un `*` impide arrancar. Comprobado con un `OPTIONS` a producción y con las pruebas de `test_endurecimiento.py`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`e76978a`](https://github.com/LewMontes/Proyecto-EIF509/commit/e76978a60ede63cfef683834192b56f76c496ede) |
| 6 | **No hay secretos en el repositorio ni en su historial** | ✅ Ningún secreto real. `git log -p --all \| grep -i -E "password\|secret\|token"` solo encuentra valores de prueba y las credenciales de desarrollo local de Docker (`gastonomo_local`), que no se usan fuera de la máquina. Faltaba exigir la clave JWT en producción, y había una contraseña por defecto de una cuenta demo sin uso. | 🟡 | Con `GASTONOMO_ENTORNO=produccion` la app no arranca sin una clave JWT de ≥ 32 caracteres; se borraron los campos demo. Los secretos del despliegue viven en GitHub Secrets y en la plataforma. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |
| 7 | **Las claves se guardan con BCrypt y el JWT expira** | ✅ bcrypt con costo 12 y sal por hash. El JWT lleva `exp` (60 minutos), `leer_token` lo exige (`options={"require": ["sub", "exp"]}`) y fija el algoritmo HS256. | ✅ | `src/app/business/seguridad/contrasenas.py` y `tokens.py`; `test_el_token_lleva_el_titular_y_el_rol_pero_ningun_dato_sensible` verifica las *claims*. | — |
| 8 | **Las dependencias no tienen vulnerabilidades conocidas** | `pip-audit` encontró **37 CVE en `pillow`**, que entraba solo por `reportlab`; ni `reportlab` ni `openpyxl` se usaban. Y no había nada que avisara de un CVE nuevo entre pushes. | 🔴 | Se quitaron las dos dependencias; el CI corre `pip-audit` en cada push y no despliega con un CVE conocido. **Dependabot** activado para `pip` y `github-actions`, con alertas en el repositorio. | [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) · [`8ccd393`](https://github.com/LewMontes/Proyecto-EIF509/commit/8ccd3936fa15d420c8ac40b6e6807669c798e5a0) |

El límite de intentos de login y las cabeceras de seguridad, que no están en la lista de la lámina
28, se documentan en las filas A07 y A02 de la sección 2.

---

## 2 · OWASP Top 10:2025

| Categoría | Qué se revisó | Hallazgo | Riesgo | Corrección aplicada / cómo se comprobó | Commit |
|---|---|---|---|---|---|
| **A01 · Broken Access Control** (incluye SSRF) | Autorización por rol y por propiedad; `usuario_id` nunca aceptado del cliente; llamadas salientes. | ✅ El titular sale siempre del token. Las únicas llamadas salientes (BCCR y Hacienda) van a URLs fijas: ningún parámetro del cliente decide a dónde se conecta el servidor. | ✅ | Ver verificación 1. SSRF comprobado en `tipo_cambio_service.py:51-54`. | — |
| **A02 · Security Misconfiguration** | CORS, cabeceras, documentación de la API, usuario del contenedor, modo producción. | CORS permisivo (verificación 5). Ninguna cabecera de seguridad en las respuestas. **Swagger UI, ReDoc y `/openapi.json` públicos en producción** (el ejemplo de A02 de la lámina 6: «Swagger expuesto sin control»): `GET /docs` y `/openapi.json` respondían 200 en `proyecto-eif509.onrender.com`. Una imagen de `python:*-slim` sin `USER` corre la app como **root**. | 🟠 | CORS (verificación 5). Middleware `CabecerasDeSeguridad`: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS, CSP `default-src 'none'` y `Cache-Control: no-store` en `/api/` (`test_toda_respuesta_lleva_las_cabeceras_de_seguridad`). La documentación se publica según `GASTONOMO_DOCS_PUBLICAS`, **cerrada por defecto en producción** (404) y abierta en desarrollo (`test_en_produccion_la_documentacion_de_la_api_no_se_publica`). El `Dockerfile` de despliegue crea y usa el usuario `gastonomo` (uid 10001); comprobado con `docker exec … id -un`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`5faaf71`](https://github.com/LewMontes/Proyecto-EIF509/commit/5faaf71cadae3cf9469c4fae0ea88b06ddb60b46) · [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) · [`e76978a`](https://github.com/LewMontes/Proyecto-EIF509/commit/e76978a60ede63cfef683834192b56f76c496ede) |
| **A03 · Software Supply Chain Failures** | Dependencias y su auditoría continua. | 37 CVE en una dependencia transitiva de una dependencia sin uso (verificación 8). | 🔴 | Ver verificación 8. | [`9e5cf7e`](https://github.com/LewMontes/Proyecto-EIF509/commit/9e5cf7e42e9da16ca22bf56b6f5d2fb422264af4) |
| **A04 · Cryptographic Failures** | Firma de los JWT, hash de contraseñas, datos en el token. | ✅ HS256 con `algorithms` fijado (un token `alg: none` no pasa); `exp` obligatorio. El token solo lleva `sub`, `rol`, `iat`, `exp`. Faltaba exigir una clave fuerte en producción (verificación 6). | 🟠 | Ver verificaciones 6 y 7. Comprobado por `test_el_token_lleva_el_titular_y_el_rol_pero_ningun_dato_sensible`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) |
| **A05 · Injection** | SQL, NoSQL (Mongo) y *log injection*. | ✅ SQL y Mongo van por el ORM y el driver con documentos, nunca con cadenas armadas. Riesgo nuevo de *log injection* al aceptar `X-Request-ID` del cliente. | 🟡 | El `X-Request-ID` del cliente se acepta solo si calza `^[A-Za-z0-9._-]{1,64}$`; si no, se genera uno (`test_el_id_de_peticion_del_cliente_se_respeta_si_es_seguro`). | [`5faaf71`](https://github.com/LewMontes/Proyecto-EIF509/commit/5faaf71cadae3cf9469c4fae0ea88b06ddb60b46) |
| **A06 · Insecure Design** | Dónde se validan las reglas de negocio; escrituras concurrentes sobre el mismo dato. | ✅ Las reglas de negocio se validan en la capa de servicio del backend, no solo en un cliente (el ejemplo de A06 de la lámina 6): montos, fechas, cuadre del desglose, categorías hoja, transiciones del comprobante y demás lanzan errores de `app.business.errors` que salen como 400/422, así que una llamada directa a la API no se las salta. Pero `presupuesto.monto_consumido` se leía, sumaba y escribía desde cuatro caminos sin control: dos compras simultáneas de la misma categoría y mes **perdían una de las dos sin error** (*lost update*). | 🔴 | Bloqueo optimista: columna `version` (migración `V9`) como `version_id_col`; el conflicto sale como `409` Problem Details. Pruebas con dos transacciones reales en SQLite y PostgreSQL. | [`042d1df`](https://github.com/LewMontes/Proyecto-EIF509/commit/042d1df9c7228fb16ba6594ef2b9adfe89d0856e) · [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |
| **A07 · Authentication Failures** | Fuerza bruta, enumeración de cuentas, vida del token. | `POST /api/v1/auth/login` aceptaba intentos ilimitados contra una cuenta. ✅ El mensaje de error ya era el mismo para correo inexistente y contraseña equivocada; el token vive 60 minutos. | 🔴 | `LimitadorDeIntentos`: 5 fallos en 15 minutos bloquean esa cuenta 15 minutos → `429` con `Retry-After`. Se cuentan también los correos que no existen, para que el bloqueo no delate cuáles sí. Pruebas en `test_endurecimiento.py` y `test_eventos_de_seguridad.py`. | [`3381915`](https://github.com/LewMontes/Proyecto-EIF509/commit/3381915850296ef487fa66968ea085b8c0bfeea4) · [`36f6e4b`](https://github.com/LewMontes/Proyecto-EIF509/commit/36f6e4baeefa5f1fd64b6da0098d5cd0393228de) |
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
