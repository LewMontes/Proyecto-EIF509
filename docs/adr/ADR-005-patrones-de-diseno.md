# ADR-005 · Patrones de diseño: Repository, Specification, Cadena de responsabilidad y State

## Estado y fecha

**Aceptada** · Fecha: 04/10/2026 · Responsables: Jose Alexis Solís Carvajal y Luis Antonio Montes de Oca Ruiz

Registrada en la Sesión 15. Reúne decisiones tomadas en el Laboratorio 3 (Repository), el
Laboratorio 4 (Cadena de responsabilidad y State, rehechos tras su retroalimentación) y el
Laboratorio 5 (Specification).

## Contexto

Cuatro puntos del código mostraron la misma señal: una regla que crecía a fuerza de condicionales o
que se repetía en varios lugares.

1. **Acceso a datos.** Catorce entidades relacionales y una colección de MongoDB. Si los servicios
   consultaran la sesión directamente, el filtro por titular dependería de que nadie lo olvide en
   cada consulta, y la regla «el servicio es el dueño del `commit`» no tendría dónde sostenerse.
2. **Filtros de la lista de compras.** `GET /api/v1/compras` admite diez filtros combinables. Con un
   parámetro por filtro, cada filtro nuevo agregaba un parámetro y un `if` al repositorio.
3. **Categorización.** La categoría sale de tres fuentes con una precedencia clara —lo que eligió el
   titular, sus reglas, la sugerencia del comercio—, y la decisión estaba escrita **dos veces**, una en
   cada proceso, como `if/elif` anidados.
4. **Ciclo de vida del comprobante.** Cinco estados, y lo que se puede pedir depende del estado. Cada
   operación de la ingesta empezaba con su propio `if comprobante.estado in (...)`.

La retroalimentación del Laboratorio 4 pidió además que los patrones estuvieran **implementados como
tales**, no solo nombrados.

## Decisión

Aplicamos un patrón **solo donde apareció la señal**, y cada uno tiene su prueba:

| Patrón | Dónde | Qué resuelve | Prueba |
|---|---|---|---|
| **Repository** (con base genérica) | `BaseRepository[TEntidad]` y 14 repositorios en [`data/repositories/`](../../src/app/data/repositories/), más `BitacoraRepository` para MongoDB | El único lugar que consulta datos; agrega con `flush` y nunca confirma; busca con `obtener_de_usuario(id, usuario_id)` | `tests/integracion/test_consultas_postgres.py` |
| **Specification** | [`especificaciones.py`](../../src/app/data/repositories/especificaciones.py) | Cada filtro es un objeto con nombre de negocio que se compone con `y` / `o`; el repositorio recibe una sola especificación | `tests/test_paginacion_api.py` |
| **Cadena de responsabilidad** | [`categorizacion.py`](../../src/app/business/services/categorizacion.py) | Cada eslabón resuelve la categoría o pasa al siguiente; la precedencia es el orden de la cadena | `tests/test_patrones.py` |
| **State** | [`ciclo_comprobante.py`](../../src/app/business/services/ciclo_comprobante.py) | Cada estado es una clase que acepta o rechaza sus transiciones; la regla de los tres intentos vive en `Parseado` | `tests/test_patrones.py` |

El detalle de la cadena y del State está en [Capa de negocio § 6](../negocio.md#6--patrones-de-diseño-aplicados);
el de Repository en [Persistencia § 3](../persistencia.md#3--repositorios-con-generalización) y el de
Specification en [API § 4.3](../api.md#43--los-filtros-de-negocio-con-specifications).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| **Condicionales anidados** para la categorización (lo que había antes) | La precedencia quedaba en la forma del `if`, una cuarta fuente obligaba a reabrir el bloque y reordenar los `elif`, y la decisión estaba duplicada en los dos procesos. |
| **Strategy** para la categorización | Una estrategia elige **un** algoritmo; aquí hacen falta varios en orden, cayendo al siguiente cuando uno no resuelve. Eso es una cadena, no una estrategia. |
| **Enum con `if` por operación** para el comprobante | Cada regla nueva —`FALLIDO` al tercer intento, pendiente sin tipo de cambio— agregaba un `if` en cada operación. Con State la regla vive en la clase del estado donde ocurre. |
| **Un parámetro por filtro** en `CompraRepository` | Cada filtro nuevo cambiaba la firma del repositorio. Con Specification un filtro nuevo es una función y una línea en el servicio. |
| **Consultar la sesión desde los servicios**, sin repositorios | El filtro por titular quedaría repartido por toda la capa de negocio. Si una consulta lo olvidara, nada de arriba se daría cuenta de que devolvió datos de otra persona. |
| **Contar los comandos inmutables como patrón *Command*** (así se presentaron en el Laboratorio 4) | No encapsulan una operación ejecutable con su receptor, no se encolan ni se deshacen: son DTOs de entrada. Se dejaron anotados como lo que son, no como un patrón. |

## Consecuencias

**Lo que se gana**

- Una fuente de categoría nueva es un eslabón nuevo, sin tocar los anteriores. Los dos procesos
  arman la misma cadena y difieren en **una línea**: el registro manual pone primero lo que eligió el
  titular.
- La idempotencia de la ingesta sale gratis del State: un comprobante `PROCESADO` que se intenta
  conciliar otra vez cae en la clase base y se rechaza.
- Los eslabones reciben funciones y no repositorios, así que se prueban con una lista en memoria.
- El aislamiento entre titulares se sostiene en la capa de datos (`obtener_de_usuario`), no en la
  disciplina de cada servicio.

**Lo que se asume**

- **Más clases e indirección.** Cinco clases de estado para un enum de cinco valores, y tres
  eslabones con su protocolo. Quien lee por primera vez tiene que seguir más archivos que con un `if`.
- **El orden de la cadena es un contrato silencioso.** Armarla en otro orden cambia la precedencia
  sin ningún error; solo lo atrapa `tests/test_patrones.py`.
- **El estado no se persiste como objeto**: `estado_de(comprobante)` lo reconstruye desde la columna
  en cada uso.
- **Las especificaciones son expresiones de SQLAlchemy.** No sirven para filtrar en memoria ni en
  MongoDB, y `BitacoraRepository` no hereda de la base genérica porque Mongo no tiene sesión ni
  transacción.
