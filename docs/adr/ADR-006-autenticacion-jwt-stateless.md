# ADR-006 · Autenticación: JWT de acceso *stateless*, bcrypt y dos roles

## Estado y fecha

**Aceptada** · Fecha: 04/10/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

Endurecida el 25/10/2026 en el Laboratorio 7 (límite de intentos y clave obligatoria en producción).
Registrada en la Sesión 15.

## Contexto

El sistema es multiusuario y guarda el gasto de cada persona: **nadie puede ver los datos de otro**,
y ese es el riesgo número uno de OWASP para APIs (*Broken Object Level Authorization*). Además:

- La propuesta define dos actores humanos: el **titular**, dueño de sus datos, y el
  **administrador**, que gestiona el catálogo compartido de comercios y no ve las compras de nadie.
- La API la consumen clientes distintos (Swagger UI, `curl`, la colección `.http` y un frontend
  React previsto), y se despliega en una plataforma que puede reiniciar o mover la instancia.
- FastAPI no trae un equivalente de Spring Security: lo que no escribamos, no existe
  ([ADR-001](ADR-001-eleccion-del-stack.md)).

## Decisión

Autenticamos con **correo y contraseña** (hash **bcrypt**, costo 12) que se canjean en
`POST /api/v1/auth/login` por un **JWT de acceso firmado con HS256**, que vive 60 minutos y es la
única sesión: el servidor no guarda nada. La autorización tiene dos niveles: **rol por endpoint**
(`TITULAR` / `ADMIN`) y **propiedad del recurso en el servicio**, con el `usuario_id` tomado siempre
del `sub` del token.

Las piezas: [`contrasenas.py`](../../src/app/business/seguridad/contrasenas.py),
[`tokens.py`](../../src/app/business/seguridad/tokens.py),
[`intentos.py`](../../src/app/business/seguridad/intentos.py),
[`auth_service.py`](../../src/app/business/services/auth_service.py) y la cadena
`obtener_usuario_actual` → `exigir_rol` de
[`dependencies.py`](../../src/app/presentation/dependencies.py). El detalle está en
[API § 5](../api.md#5--seguridad).

Reglas que forman parte de la decisión:

- El token lleva solo `sub`, `rol`, `iat` y `exp`. Va firmado, no cifrado: no lleva datos sensibles.
- `leer_token` fija `algorithms=["HS256"]` y exige `sub` y `exp`: un token `alg: none` no pasa.
- **El rol que vale es el de la base:** cada petición relee la cuenta por llave primaria.
- Registrarse siempre crea un `TITULAR`; el único `ADMIN` nace al arrancar, de variables de entorno.
- Mismo error para correo inexistente y contraseña equivocada; **5 fallos en 15 minutos** bloquean
  esa cuenta 15 minutos (`429` con `Retry-After`).
- El secreto JWT vive en la variable `GASTONOMO_JWT_SECRETO` de la plataforma. Con
  `GASTONOMO_ENTORNO=produccion` la app **no arranca** sin una clave de al menos 32 caracteres.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| **Sesión de servidor con cookie** | Obliga a guardar estado (tabla o almacén de sesiones) y a compartirlo si hay más de una instancia, y con cookies hay que defenderse además de CSRF. Con el token en el encabezado `Authorization`, cada petición se autentica sola. |
| ***Refresh token* además del de acceso** | Exige guardar los tokens de refresco del lado del servidor para poder revocarlos, que es justo el estado que el diseño evita. Se eligió un token de 60 minutos y volver a iniciar sesión. |
| **RS256** (par de claves pública y privada) | Sirve cuando otro servicio tiene que verificar tokens sin poder firmarlos. Aquí firma y verifica la misma aplicación, así que una clave simétrica alcanza y es más simple de administrar. |
| **Confiar en el rol que trae el token** | Quitarle el rol a alguien, o desactivarlo, no surtiría efecto hasta que el token venciera, salvo con una lista de tokens revocados. Releer la cuenta cuesta una consulta por llave primaria. |
| **Delegar todo el inicio de sesión a Google (OIDC)** | Ataría la cuenta a un proveedor externo y dejaría fuera a quien no quiera usarlo. El esquema quedó preparado para sumarlo como segunda vía (`google_id` y el `CHECK` de la migración `V7`), no como la única. |
| **Limitar los intentos por IP** | Una universidad o una red móvil comparten IP, y quien ataca cambia de IP sin esfuerzo. Lo que no cambia es la cuenta atacada. |

## Consecuencias

**Lo que se gana**

- La API es *stateless*: dos peticiones del mismo cliente pueden caer en instancias distintas sin
  compartir nada, y un reinicio de la plataforma no cierra sesiones (con la clave fija).
- Ningún endpoint acepta `usuario_id`: lo ajeno responde `404`, indistinguible de lo inexistente.
  Lo prueban `test_404_lo_de_otro_titular_es_indistinguible_de_lo_que_no_existe` y
  `test_mandar_usuario_id_en_el_cuerpo_no_cambia_el_dueno`.
- Desactivar una cuenta surte efecto en la siguiente petición.
- Cada intento fallido, bloqueo y acceso denegado queda registrado como evento de seguridad, sin
  contraseñas ni tokens.

**Lo que se asume**

- **Un token robado vale hasta que vence** (60 minutos). No hay `logout` del lado del servidor ni
  lista de revocación; la única revocación inmediata es desactivar la cuenta.
- **Una consulta extra por petición** para releer la cuenta.
- **El límite de intentos vive en memoria del proceso.** Con una sola instancia alcanza; con varias,
  cada una contaría por separado y haría falta un almacén compartido (Redis).
- **El bloqueo por cuenta permite bloquear a otro a propósito** durante 15 minutos. Es temporal y
  queda registrado como `inicio_sesion_bloqueado`.
- Quien conozca `GASTONOMO_JWT_SECRETO` puede fabricar un token de cualquier cuenta: la clave nunca
  va en el repositorio y cambiarla invalida todos los tokens emitidos.
