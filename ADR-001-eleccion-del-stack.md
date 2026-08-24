# ADR-001 · Elección del stack tecnológico

## Estado

**Aceptada** · Fecha: 08/08/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

## Contexto

Tenemos que elegir el stack sobre el que se construirán los laboratorios y por ende el proyecto
final de este curso.

Para poder elegir el stack tomamos en cuenta las siguientes restricciones:

- **Tiempo:** un ciclo de seis meses, siete laboratorios incrementales.
- **El dominio es de cálculo.** La app es un sistema de gasto personal: obtiene las compras de los
  comprobantes que llegan por correo, convierte monedas, acumula presupuestos y grafica todo. El
  valor del sistema está en que los números cuadren y en poder explicar de dónde salió cada total.
- **El frontend debe mostrar el gasto en vivo.** Cuando se genera una compra, el presupuesto
  tiene que actualizarse sin recargar la página.
- **Una sola base de datos.** El sistema no almacena los comprobantes: lee cada correo, le extrae
  los datos que necesita y descarta el contenido. Todo lo que se persiste tiene esquema fijo, así
  que una base relacional lo cubre entero.
- **Experiencia del equipo:** ambos integrantes trabajamos con Python de forma constante en otros
  cursos y en nuestra experiencia laboral; con Java tenemos base pero mucho menos rodaje.

## Decisión

Usaremos **Python 3.14 + FastAPI + PostgreSQL + React** como stack principal, organizados en la
misma arquitectura por capas que pide el curso.

| Pieza | Elección | Por qué |
|---|---|---|
| Lenguaje | **Python** | El ecosistema de cálculo y graficación del proyecto vive aquí. `Decimal` en la biblioteca estándar nos da aritmética exacta para montos. |
| Framework web | **FastAPI** | API-first, validación declarativa con Pydantic, OpenAPI generado solo, inyección de dependencias nativa y WebSockets para el gasto en vivo. |
| ORM | **SQLAlchemy 2.0** | Mapeo declarativo tipado, control explícito del límite transaccional y sesión por request. |
| Migraciones | **Alembic** | Versiona el esquema en el repositorio, igual que haría Flyway o Liquibase en el mundo Java. |
| Base relacional | **PostgreSQL** | Es la que recomienda el curso. `NUMERIC` de precisión exacta para dinero y transacciones ACID reales para el proceso de conciliación. |
| Frontend | **React** | Es lo que recomienda el curso y se comunica con FastAPI por JSON y WebSocket sin fricción. |
| Pruebas | **pytest** | Sintaxis directa, fixtures componibles, cliente de pruebas HTTP integrado con FastAPI. |
| Calidad | **ruff** | Hace de linter y formateador en una sola herramienta. Es lo que ocupa el lugar del compilador en la CI. |

**Sobre la separación por capas:** la organización en `presentation / business / data / config`
se mantiene idéntica a la del curso, con la misma regla de dependencias
(presentación → negocio → datos, nunca al revés).

## Alternativas consideradas

### 1. Java 21 + Spring Boot 3 + Gradle (la recomendación del curso)

Es el stack de referencia y descartarlo tiene un costo real que asumimos con los ojos abiertos.

**A favor:** es el lenguaje del curso, los ejemplos y las plantillas están hechos en él; Spring
Data JPA resuelve el acceso a datos con muy poco código; `@Transactional` hace el límite
transaccional del Proceso 2 casi gratis; el compilador atrapa errores que en Python solo
aparecen al ejecutar; y el profesor puede revisarlo sin cambiar de contexto.

**Por qué lo descartamos:** el peso del proyecto está en la parte analítica —desglose,
conversión histórica de monedas, acumulados de presupuesto y graficación— y esa parte la
escribimos y verificamos mucho más rápido en Python. Sumado a que el equipo tiene bastante más
rodaje en Python que en Java, estimamos que con Spring gastaríamos una porción significativa del
ciclo peleando con el framework en vez de con el dominio. Con siete laboratorios encadenados y
dos personas, ese tiempo no lo tenemos.

### 2. Node.js + Express + TypeScript

Sería el mismo lenguaje en el backend y en el frontend, lo que reduce el costo de cambiar de
contexto, y su modelo asíncrono sirve igual de bien para el gasto en vivo.

**Por qué lo descartamos:** el manejo de dinero exige aritmética decimal exacta, y en JavaScript
eso obliga a meter una biblioteca de terceros (`decimal.js`, `big.js`) y a recordar usarla en
cada operación; un solo `+` olvidado introduce un error de redondeo silencioso en un reporte
financiero. Python trae `Decimal` en la biblioteca estándar. Además, Express no trae validación
ni documentación de API: habría que armar a mano con Zod y `swagger-jsdoc` lo que FastAPI da de
fábrica.

### 3. Django + Django REST Framework

Es el stack "baterías incluidas" de Python: ORM propio, panel de administración gratis,
autenticación y permisos ya resueltos —cosas que nos servirían cuando toque el control de acceso.

**Por qué lo descartamos:** Django organiza el código por *apps*, y cada app mezcla modelos,
vistas y lógica en el mismo paquete. Eso choca de frente con la separación estricta en tres capas
que la rúbrica evalúa, y nos dejaría o peleando contra las convenciones del framework o
entregando una estructura que no refleja lo que se nos pide. FastAPI no impone ninguna estructura,
así que podemos calcar la que enseña el curso. También pesó que el soporte asíncrono de Django
sigue siendo parcial y el nuestro es un requisito de tiempo real.

### 4. Flask + SQLAlchemy

El más liviano y el más fácil de explicar en una defensa oral, con el mismo ORM que ya elegimos.

**Por qué lo descartamos:** hay que construir a mano la validación de entrada, la documentación
OpenAPI, la inyección de dependencias y el soporte asíncrono. Es exactamente el mismo trabajo que
FastAPI ya hizo, sin nada a cambio.

## Consecuencias

### Positivas

- La lógica de cálculo del dominio queda en el lenguaje donde el equipo es más productivo, y las
  fórmulas se prueban una por una como funciones puras sin levantar la aplicación.
- `Decimal` en la biblioteca estándar y `NUMERIC` en PostgreSQL nos dan aritmética exacta de punta
  a punta, sin dependencias extra.
- FastAPI genera la documentación OpenAPI sola: cuando se construya el frontend React, tendrá el
  contrato de la API sin que nadie lo escriba ni lo mantenga.
- Los WebSockets nativos cubren el requisito de mostrar el gasto en vivo sin agregar
  infraestructura.
- La CI es más rápida que una de Gradle, así que da retroalimentación en cada push sin que se
  vuelva molesta.

### Negativas

Estas son las que nos cuesta la decisión, y son reales:

- **Perdemos el compilador.** Java atrapa en tiempo de compilación errores que en Python explotan
  en ejecución. Lo compensamos con anotaciones de tipo en todo el código, `ruff` corriendo en la CI
  y la disciplina de probar cada regla de negocio, pero es una red de seguridad que hay que
  mantener a pulso en vez de recibirla gratis.
- **Perdemos `@Transactional`.** El límite transaccional hay que manejarlo
  explícitamente con la sesión de SQLAlchemy. Es más código y más fácil de equivocar que una
  anotación.
- **Nos salimos del material del curso.** Los ejemplos, plantillas y explicaciones de clase están
  en Java: cada vez que el profesor muestre algo, nos toca traducirlo.
- **Menos ayuda del framework en próximos laboratorios.** Spring Security resuelve autenticación y
  roles con configuración; en FastAPI hay que escribir esa parte.
- **Riesgo de que las capas se filtren.** Python no impide que un router importe un repositorio.
  Mantener la regla de dependencias depende de nuestra disciplina y de la revisión mutua en los
  *pull requests*.

### Neutras

- **En el Laboratorio 1 la base es SQLite, no PostgreSQL.** Es deliberado y temporal: permite que
  el esqueleto arranque y funcione completo sin pedirle a nadie —ni a la CI— que instale un
  servidor de base de datos. Como el acceso a datos pasa entero por SQLAlchemy y los repositorios,
  el cambio a PostgreSQL se reduce a cambiar la URL de conexión y agregar Alembic. Es justamente la
  clase de sustitución que la separación por capas debe permitir; si nos costara más que eso, sería
  señal de que la capa de datos se filtró hacia arriba.
- Todo el equipo trabaja con Python 3.14 y con el mismo entorno virtual, y la CI corre esa misma
  versión, para que no haya diferencias entre máquinas.
- Las dependencias se declaran en `pyproject.toml`, que cumple el papel del `build.gradle`.
- El comando de arranque cambia (`uvicorn app.main:app` en vez de `./gradlew bootRun`) y quedó
  documentado en el README.

## Referencias

- Guía del Laboratorio 1 · EIF509 · II Ciclo 2026, sección «Stack de referencia»: autoriza stacks
  alternativos equivalentes solicitados por escrito.
- Documentación oficial de FastAPI — inyección de dependencias y proyectos grandes.
- Documentación oficial de SQLAlchemy 2.0 — ORM declarativo y manejo de sesiones.
- Módulo `decimal` de la biblioteca estándar de Python — aritmética decimal exacta.
- Sesión 2 del curso EIF509 — arquitectura de software, capas y niveles.
